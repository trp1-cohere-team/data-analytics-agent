"""Unit tests for agent/memory/manager.py.

Covers:
  - save_session: writes file, write-once (second call no-ops), concurrent lock safety
  - load_session: returns None for missing, returns SessionTranscript for saved
  - get_topics: empty on fresh dir, merges data after consolidation
  - _merge_session_into_topics: additive (no removals), dedup by session_id
  - _write_topics_atomic: writes all 3 files, wipes stale staging, cleans up on success
  - autoDream: skips young sessions, processes stale ones, respects delete setting
  - PBT-U3-04: Write-once session count invariant (100 examples)
  - PBT-U3-05: Topic merge idempotency (150 examples)
  - PBT-U3-06: SessionMemory round-trip (200 examples)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent.memory.manager import MemoryManager
from agent.models import SessionMemory, SessionTranscript, TraceStep
from tests.unit.strategies import (
    INVARIANT_SETTINGS,
    session_memory_objects,
    session_transcripts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mgr(tmp_path: Path, max_age_days: int = 7, delete: bool = True) -> MemoryManager:
    return MemoryManager(
        memory_dir=tmp_path,
        max_age_days=max_age_days,
        delete_after_consolidation=delete,
        autodream_poll_s=99999,   # disable background polling in unit tests
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _transcript(session_id: str | None = None, timestamp: float | None = None) -> SessionTranscript:
    return SessionTranscript(
        session_id=session_id or str(uuid.uuid4()),
        timestamp=timestamp or time.time(),
        history=[
            TraceStep(
                iteration=1,
                thought="test thought",
                action="query_database",
                action_input={},
                observation="test obs",
                timestamp=time.time(),
            )
        ],
        summary="test summary",
    )


# ---------------------------------------------------------------------------
# save_session
# ---------------------------------------------------------------------------

class TestSaveSession:
    def test_writes_session_file(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        _run(mgr.save_session(sid, [], "hello"))
        assert (tmp_path / "sessions" / f"{sid}.json").exists()

    def test_write_once_second_call_noop(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        _run(mgr.save_session(sid, [], "first"))
        mtime1 = (tmp_path / "sessions" / f"{sid}.json").stat().st_mtime
        _run(mgr.save_session(sid, [], "second"))   # should be no-op
        mtime2 = (tmp_path / "sessions" / f"{sid}.json").stat().st_mtime
        assert mtime1 == mtime2   # file unchanged

    def test_persists_summary_and_history(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        steps = [
            TraceStep(
                iteration=1, thought="t", action="query_database",
                action_input={}, observation="obs", timestamp=1.0,
            )
        ]
        _run(mgr.save_session(sid, steps, "my summary"))
        raw = (tmp_path / "sessions" / f"{sid}.json").read_text()
        data = json.loads(raw)
        assert data["summary"] == "my summary"
        assert len(data["history"]) == 1

    def test_concurrent_saves_same_id_only_one_file(self, tmp_path):
        """Concurrent saves for same session_id: only the first writer wins."""
        mgr = _mgr(tmp_path)

        async def _concurrent():
            await mgr.initialise()
            sid = str(uuid.uuid4())
            await asyncio.gather(*[mgr.save_session(sid, [], f"attempt-{i}") for i in range(5)])
            return sid

        sid = _run(_concurrent())
        raw = (tmp_path / "sessions" / f"{sid}.json").read_text()
        data = json.loads(raw)
        assert data["session_id"] == sid


# ---------------------------------------------------------------------------
# load_session
# ---------------------------------------------------------------------------

class TestLoadSession:
    def test_returns_none_for_missing(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        result = _run(mgr.load_session("no-such-session"))
        assert result is None

    def test_returns_transcript_for_saved(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        _run(mgr.save_session(sid, [], "test summary"))
        loaded = _run(mgr.load_session(sid))
        assert loaded is not None
        assert loaded.session_id == sid
        assert loaded.summary == "test summary"


# ---------------------------------------------------------------------------
# get_topics
# ---------------------------------------------------------------------------

class TestGetTopics:
    def test_empty_on_fresh_dir(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        topics = _run(mgr.get_topics())
        assert topics.successful_patterns == []
        assert topics.query_corrections == []
        assert topics.user_preferences == {}

    def test_loads_after_write(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        patterns = [{"session_id": "abc", "summary": "good pattern"}]
        (tmp_path / "topics" / "successful_patterns.json").write_text(json.dumps(patterns))
        topics = _run(mgr.get_topics())
        assert len(topics.successful_patterns) == 1
        assert topics.successful_patterns[0]["summary"] == "good pattern"

    def test_missing_file_returns_empty(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        # Only write patterns, not corrections
        (tmp_path / "topics" / "successful_patterns.json").write_text("[]")
        topics = _run(mgr.get_topics())
        assert topics.query_corrections == []


# ---------------------------------------------------------------------------
# _merge_session_into_topics
# ---------------------------------------------------------------------------

class TestMergeSessionIntoTopics:
    def test_additive_no_removal(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        existing = SessionMemory(
            successful_patterns=[{"session_id": "old-id", "summary": "old"}],
            query_corrections=[],
            user_preferences={},
        )
        t = _transcript()
        merged = mgr._merge_session_into_topics(t, existing)
        # Old pattern still present
        sids = {p["session_id"] for p in merged.successful_patterns}
        assert "old-id" in sids

    def test_deduplicates_by_session_id(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        existing = SessionMemory(
            successful_patterns=[{"session_id": sid, "summary": "already here"}],
            query_corrections=[],
            user_preferences={},
        )
        t = _transcript(session_id=sid)
        merged = mgr._merge_session_into_topics(t, existing)
        pattern_sids = [p["session_id"] for p in merged.successful_patterns]
        assert pattern_sids.count(sid) == 1   # not duplicated

    def test_appends_new_session(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        existing = SessionMemory(
            successful_patterns=[],
            query_corrections=[],
            user_preferences={},
        )
        t = _transcript()
        merged = mgr._merge_session_into_topics(t, existing)
        assert len(merged.successful_patterns) == 1
        assert merged.successful_patterns[0]["session_id"] == t.session_id


# ---------------------------------------------------------------------------
# _write_topics_atomic
# ---------------------------------------------------------------------------

class TestWriteTopicsAtomic:
    def test_writes_all_three_files(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        topics = SessionMemory(
            successful_patterns=[{"session_id": "x", "summary": "ok"}],
            user_preferences={"pref": "val"},
            query_corrections=[{"session_id": "y", "corrections": []}],
        )
        _run(mgr._write_topics_atomic(topics))
        assert (tmp_path / "topics" / "successful_patterns.json").exists()
        assert (tmp_path / "topics" / "user_preferences.json").exists()
        assert (tmp_path / "topics" / "query_corrections.json").exists()

    def test_cleans_up_staging_on_success(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        topics = SessionMemory()
        _run(mgr._write_topics_atomic(topics))
        assert not (tmp_path / ".staging").exists()

    def test_wipes_stale_staging_before_write(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        # Pre-create a stale staging dir with a stale file
        staging = tmp_path / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "stale.json").write_text("[stale data]")
        topics = SessionMemory()
        _run(mgr._write_topics_atomic(topics))
        # After atomic write, staging should be cleaned up
        assert not staging.exists()

    def test_round_trip_data_integrity(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        original = SessionMemory(
            successful_patterns=[{"session_id": "abc", "summary": "pattern"}],
            user_preferences={"key": "value"},
            query_corrections=[],
        )
        _run(mgr._write_topics_atomic(original))
        loaded = _run(mgr.get_topics())
        assert loaded.successful_patterns == original.successful_patterns
        assert loaded.user_preferences == original.user_preferences


# ---------------------------------------------------------------------------
# autoDream cycle
# ---------------------------------------------------------------------------

class TestAutoDream:
    def test_skips_young_sessions(self, tmp_path):
        mgr = _mgr(tmp_path, max_age_days=7, delete=True)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        _run(mgr.save_session(sid, [], "young"))
        # Cycle should not process fresh session
        _run(mgr._autodream_cycle())
        assert (tmp_path / "sessions" / f"{sid}.json").exists()   # not deleted

    def test_processes_stale_sessions(self, tmp_path):
        mgr = _mgr(tmp_path, max_age_days=1, delete=True)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        # Write session manually with old timestamp
        stale_ts = time.time() - 2 * 86_400   # 2 days ago
        transcript = SessionTranscript(
            session_id=sid,
            timestamp=stale_ts,
            history=[],
            summary="stale session",
        )
        session_path = tmp_path / "sessions" / f"{sid}.json"
        session_path.write_text(json.dumps(transcript.model_dump(), default=str))
        _run(mgr._autodream_cycle())
        # Stale session should be consolidated into topics
        topics = _run(mgr.get_topics())
        sids = {p["session_id"] for p in topics.successful_patterns}
        assert sid in sids

    def test_respects_delete_false(self, tmp_path):
        mgr = _mgr(tmp_path, max_age_days=1, delete=False)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        stale_ts = time.time() - 2 * 86_400
        transcript = SessionTranscript(
            session_id=sid,
            timestamp=stale_ts,
            history=[],
            summary="stale",
        )
        session_path = tmp_path / "sessions" / f"{sid}.json"
        session_path.write_text(json.dumps(transcript.model_dump(), default=str))
        _run(mgr._autodream_cycle())
        assert session_path.exists()   # NOT deleted because delete=False

    def test_respects_delete_true(self, tmp_path):
        mgr = _mgr(tmp_path, max_age_days=1, delete=True)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        stale_ts = time.time() - 2 * 86_400
        transcript = SessionTranscript(
            session_id=sid,
            timestamp=stale_ts,
            history=[],
            summary="stale",
        )
        session_path = tmp_path / "sessions" / f"{sid}.json"
        session_path.write_text(json.dumps(transcript.model_dump(), default=str))
        _run(mgr._autodream_cycle())
        assert not session_path.exists()   # deleted


# ---------------------------------------------------------------------------
# MEMORY.md
# ---------------------------------------------------------------------------

class TestMemoryMd:
    def test_bootstraps_on_initialise(self, tmp_path):
        mgr = _mgr(tmp_path)
        _run(mgr.initialise())
        assert (tmp_path / "MEMORY.md").exists()
        content = (tmp_path / "MEMORY.md").read_text()
        assert "MEMORY" in content

    def test_appended_after_consolidation(self, tmp_path):
        mgr = _mgr(tmp_path, max_age_days=1, delete=False)
        _run(mgr.initialise())
        sid = str(uuid.uuid4())
        stale_ts = time.time() - 2 * 86_400
        transcript = SessionTranscript(
            session_id=sid,
            timestamp=stale_ts,
            history=[],
            summary="stale",
        )
        session_path = tmp_path / "sessions" / f"{sid}.json"
        session_path.write_text(json.dumps(transcript.model_dump(), default=str))
        _run(mgr._autodream_cycle())
        memory_content = (tmp_path / "MEMORY.md").read_text()
        assert sid in memory_content


# ---------------------------------------------------------------------------
# PBT-U3-04: Write-once session count
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=1, max_value=10))
@INVARIANT_SETTINGS["PBT-U3-04"]
def test_pbt_u3_04_write_once_count(n: int):
    """PBT-U3-04: Saving the same session_id N times yields exactly 1 file."""
    import tempfile

    async def _run_test(tmp_path):
        mgr = MemoryManager(
            memory_dir=tmp_path,
            max_age_days=7,
            delete_after_consolidation=False,
            autodream_poll_s=99999,
        )
        await mgr.initialise()
        sid = str(uuid.uuid4())
        for _ in range(n):
            await mgr.save_session(sid, [], "summary")
        return sid, tmp_path

    with tempfile.TemporaryDirectory() as td:
        sid, tmp_path = asyncio.get_event_loop().run_until_complete(_run_test(Path(td)))
        session_files = list((tmp_path / "sessions").glob("*.json"))
        assert len(session_files) == 1
        raw = session_files[0].read_text()
        assert json.loads(raw)["session_id"] == sid


# ---------------------------------------------------------------------------
# PBT-U3-05: Topic merge idempotency
# ---------------------------------------------------------------------------

@given(transcript=session_transcripts())
@INVARIANT_SETTINGS["PBT-U3-05"]
def test_pbt_u3_05_merge_idempotency(transcript: SessionTranscript):
    """PBT-U3-05: Merging same transcript twice produces same result as merging once."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mgr = MemoryManager(
            memory_dir=Path(td),
            max_age_days=7,
            delete_after_consolidation=False,
            autodream_poll_s=99999,
        )
        base = SessionMemory()
        once = mgr._merge_session_into_topics(transcript, base)
        twice = mgr._merge_session_into_topics(transcript, once)

    # Idempotent: second merge should not add new entries for the same session_id
    assert len(twice.successful_patterns) == len(once.successful_patterns)
    assert len(twice.query_corrections) == len(once.query_corrections)


# ---------------------------------------------------------------------------
# PBT-U3-06: SessionMemory round-trip
# ---------------------------------------------------------------------------

@given(memory=session_memory_objects())
@INVARIANT_SETTINGS["PBT-U3-06"]
def test_pbt_u3_06_session_memory_roundtrip(memory: SessionMemory):
    """PBT-U3-06: SessionMemory serialises and deserialises without data loss."""
    import tempfile

    async def _run_test(tmp_path):
        mgr = MemoryManager(
            memory_dir=tmp_path,
            max_age_days=7,
            delete_after_consolidation=False,
            autodream_poll_s=99999,
        )
        await mgr.initialise()
        await mgr._write_topics_atomic(memory)
        return await mgr.get_topics()

    with tempfile.TemporaryDirectory() as td:
        loaded = asyncio.get_event_loop().run_until_complete(_run_test(Path(td)))
    assert len(loaded.successful_patterns) == len(memory.successful_patterns)
    assert len(loaded.query_corrections) == len(memory.query_corrections)
    assert loaded.user_preferences == memory.user_preferences
