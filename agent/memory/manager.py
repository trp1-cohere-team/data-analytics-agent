"""Memory Manager — session persistence and topic consolidation (autoDream).

Design decisions:
  - Q2=B: per-session-id lock registry (dict[str, asyncio.Lock])
  - Q3=B: StagingTransactionWriter for atomic topic writes (.staging/ → rename)
  - Q4=D: delete-after-consolidation controlled by settings.memory_delete_after_consolidation
  - Q5=A: write-once sessions (second save_session call is a no-op)
  - Q6=C: SessionTranscript stores raw list[TraceStep] + caller-provided summary
  - Q7=B: autoDream background task (asyncio.ensure_future at __init__)
  - Q8=C: stale session threshold = settings.memory_max_age_days
  - NFR Q1=A: all disk I/O in asyncio.to_thread (non-blocking event loop)
  - NFR Q2=A: .staging/ directory used by StagingTransactionWriter
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.models import SessionMemory, SessionTranscript, TraceStep

_logger = logging.getLogger("agent.memory")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOPIC_FILES = ("successful_patterns.json", "user_preferences.json", "query_corrections.json")
_MEMORY_MD_HEADER = "# MEMORY\n\nAppend-only log of consolidated sessions.\n\n"
_AUTODREAM_POLL_S = 300   # Poll every 5 minutes for stale sessions

# ---------------------------------------------------------------------------
# AsyncFileIO helpers — Pattern 1: AsyncFileIOWrapper (NFR Q1=A)
# ---------------------------------------------------------------------------

async def _read_text(path: Path, encoding: str = "utf-8") -> str:
    return await asyncio.to_thread(path.read_text, encoding)


async def _write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    await asyncio.to_thread(path.write_text, content, encoding)


async def _replace_file(src: Path, dst: Path) -> None:
    await asyncio.to_thread(src.replace, dst)


async def _mkdir(path: Path) -> None:
    await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)


async def _file_exists(path: Path) -> bool:
    return await asyncio.to_thread(path.exists)


async def _unlink(path: Path) -> None:
    await asyncio.to_thread(path.unlink, True)  # missing_ok=True


async def _glob_json(path: Path) -> list[Path]:
    return await asyncio.to_thread(lambda: sorted(path.glob("*.json")))


async def _rmdir_tree(path: Path) -> None:
    """Remove directory and all contents (non-recursive shutil.rmtree via thread)."""
    import shutil
    await asyncio.to_thread(shutil.rmtree, path, True)

# ---------------------------------------------------------------------------
# StructuredMemoryLogger — Pattern 4 (agent.memory)
# ---------------------------------------------------------------------------

def _log_session_saved(session_id: str, trace_steps: int) -> None:
    _logger.info("session_saved", extra={"session_id": session_id, "trace_steps": trace_steps})


def _log_session_skipped(session_id: str, reason: str) -> None:
    _logger.info("session_save_skipped", extra={"session_id": session_id, "reason": reason})


def _log_session_loaded(session_id: str, found: bool) -> None:
    _logger.info("session_loaded", extra={"session_id": session_id, "found": found})


def _log_topics_written(patterns: int, corrections: int) -> None:
    _logger.info("topics_written", extra={"patterns": patterns, "corrections": corrections})


def _log_autodream_cycle(stale_count: int, consolidated: int) -> None:
    _logger.info("autodream_cycle", extra={"stale_count": stale_count, "consolidated": consolidated})


def _log_autodream_error(error: str) -> None:
    _logger.error("autodream_error", extra={"error": error[:500]})


def _log_memory_md_appended(session_id: str) -> None:
    _logger.info("memory_md_appended", extra={"session_id": session_id})

# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

class MemoryManager:
    """Session persistence and background topic consolidation.

    FR-03: layer 3 context (session memory topics).
    NFR-03: MEMORY.md append-only log pattern.

    All public methods are async (disk I/O via asyncio.to_thread).
    Exception: get_topics() reads topic files from disk — also async.

    Call initialise() once after construction to set up directories and
    launch the autoDream background task.
    """

    def __init__(
        self,
        memory_dir: str | Path | None = None,
        max_age_days: int | None = None,
        delete_after_consolidation: bool | None = None,
        autodream_poll_s: int = _AUTODREAM_POLL_S,
    ) -> None:
        self._memory_dir = Path(memory_dir or settings.memory_dir)
        self._max_age_days = max_age_days if max_age_days is not None else settings.memory_max_age_days
        self._delete_after = (
            delete_after_consolidation
            if delete_after_consolidation is not None
            else settings.memory_delete_after_consolidation
        )
        self._autodream_poll_s = autodream_poll_s

        # Derived paths
        self._sessions_dir = self._memory_dir / "sessions"
        self._topics_dir = self._memory_dir / "topics"
        self._staging_dir = self._memory_dir / ".staging"
        self._memory_md = self._memory_dir / "MEMORY.md"

        # Per-session-id lock registry (Q2=B)
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()   # guards the dict itself

        # Background task handle
        self._autodream_task: asyncio.Task[None] | None = None

    async def initialise(self) -> None:
        """Async init: create directory structure, bootstrap MEMORY.md, start autoDream.

        Must be called once after construction. Separated from __init__ because
        __init__ cannot be async and asyncio.ensure_future requires a running loop.
        """
        await _mkdir(self._sessions_dir)
        await _mkdir(self._topics_dir)

        if not await _file_exists(self._memory_md):
            await _write_text(self._memory_md, _MEMORY_MD_HEADER)

        # Launch autoDream background task (Q7=B)
        self._autodream_task = asyncio.ensure_future(self._run_autodream())

    # ------------------------------------------------------------------
    # Session lock registry (Q2=B)
    # ------------------------------------------------------------------

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Return (creating if needed) the per-session-id asyncio.Lock."""
        async with self._registry_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    # ------------------------------------------------------------------
    # Session persistence — write-once (Q5=A)
    # ------------------------------------------------------------------

    async def save_session(
        self,
        session_id: str,
        history: list[TraceStep],
        summary: str,
    ) -> None:
        """Persist a session transcript to sessions/{session_id}.json.

        Write-once (Q5=A): if the file already exists this call is a no-op.
        Per-session-id lock (Q2=B): concurrent saves for the same id are serialized.
        Stores raw list[TraceStep] + caller-provided summary (Q6=C).
        """
        lock = await self._get_session_lock(session_id)
        async with lock:
            target = self._sessions_dir / f"{session_id}.json"
            if await _file_exists(target):
                _log_session_skipped(session_id, "already_exists")
                return

            transcript = SessionTranscript(
                session_id=session_id,
                timestamp=time.time(),
                history=history,
                summary=summary,
            )
            serialised = json.dumps(transcript.model_dump(), indent=2, default=str)
            await _write_text(target, serialised)
            _log_session_saved(session_id, len(history))

    async def load_session(self, session_id: str) -> SessionTranscript | None:
        """Read sessions/{session_id}.json; returns None if not found."""
        target = self._sessions_dir / f"{session_id}.json"
        if not await _file_exists(target):
            _log_session_loaded(session_id, found=False)
            return None

        raw = await _read_text(target)
        data = json.loads(raw)
        transcript = SessionTranscript(**data)
        _log_session_loaded(session_id, found=True)
        return transcript

    # ------------------------------------------------------------------
    # Topic access
    # ------------------------------------------------------------------

    async def get_topics(self) -> SessionMemory:
        """Load the 3 topic JSON files into a SessionMemory.

        Missing files return empty defaults (not an error).
        """
        patterns: list[dict[str, Any]] = await self._load_json_list(
            self._topics_dir / "successful_patterns.json"
        )
        corrections: list[dict[str, Any]] = await self._load_json_list(
            self._topics_dir / "query_corrections.json"
        )
        preferences: dict[str, Any] = await self._load_json_dict(
            self._topics_dir / "user_preferences.json"
        )
        return SessionMemory(
            successful_patterns=patterns,
            user_preferences=preferences,
            query_corrections=corrections,
        )

    async def _load_json_list(self, path: Path) -> list[dict[str, Any]]:
        if not await _file_exists(path):
            return []
        try:
            return json.loads(await _read_text(path))
        except (json.JSONDecodeError, Exception):
            return []

    async def _load_json_dict(self, path: Path) -> dict[str, Any]:
        if not await _file_exists(path):
            return {}
        try:
            return json.loads(await _read_text(path))
        except (json.JSONDecodeError, Exception):
            return {}

    # ------------------------------------------------------------------
    # autoDream — background consolidation task (Q7=B)
    # ------------------------------------------------------------------

    async def _run_autodream(self) -> None:
        """Background loop: periodically consolidate stale sessions into topics.

        Runs forever until cancelled (e.g. on shutdown). Errors in one cycle
        are caught and logged — they do not terminate the loop.
        """
        while True:
            await asyncio.sleep(self._autodream_poll_s)
            try:
                await self._autodream_cycle()
            except Exception as exc:  # noqa: BLE001
                _log_autodream_error(str(exc))

    async def _autodream_cycle(self) -> None:
        """One autoDream pass: find stale sessions → merge → write → log → delete."""
        stale_threshold = time.time() - self._max_age_days * 86_400
        session_files = await _glob_json(self._sessions_dir)

        stale_files: list[Path] = []
        for sf in session_files:
            try:
                raw = await _read_text(sf)
                data = json.loads(raw)
                ts = float(data.get("timestamp", 0.0))
                if ts < stale_threshold:
                    stale_files.append(sf)
            except Exception:  # noqa: BLE001
                continue

        if not stale_files:
            _log_autodream_cycle(stale_count=0, consolidated=0)
            return

        topics = await self.get_topics()
        consolidated = 0

        for sf in stale_files:
            try:
                raw = await _read_text(sf)
                data = json.loads(raw)
                transcript = SessionTranscript(**data)
                topics = self._merge_session_into_topics(transcript, topics)
                consolidated += 1
            except Exception:  # noqa: BLE001
                continue

        await self._write_topics_atomic(topics)

        for sf in stale_files:
            try:
                raw = await _read_text(sf)
                data = json.loads(raw)
                session_id = data.get("session_id", sf.stem)
                await self._append_memory_md(session_id)
            except Exception:  # noqa: BLE001
                pass

        # Optional delete (Q4=D)
        if self._delete_after:
            for sf in stale_files:
                await _unlink(sf)

        _log_autodream_cycle(stale_count=len(stale_files), consolidated=consolidated)

    # ------------------------------------------------------------------
    # Topic merge — additive, dedup by session_id (MM-03)
    # ------------------------------------------------------------------

    def _merge_session_into_topics(
        self, transcript: SessionTranscript, topics: SessionMemory
    ) -> SessionMemory:
        """Merge one transcript into topics; additive only, dedup by session_id.

        - successful_patterns: append entry if session_id not already present
        - query_corrections: append entry if session_id not already present
        - user_preferences: merge keys (transcript values take precedence on conflict)
        """
        sid = transcript.session_id

        # Deduplicate pattern/correction lists by session_id
        existing_pattern_sids = {p.get("session_id") for p in topics.successful_patterns}
        new_patterns = list(topics.successful_patterns)
        if sid not in existing_pattern_sids and transcript.summary:
            new_patterns.append({"session_id": sid, "summary": transcript.summary})

        existing_correction_sids = {c.get("session_id") for c in topics.query_corrections}
        new_corrections = list(topics.query_corrections)
        if sid not in existing_correction_sids:
            # Extract correction-relevant steps from history
            correction_steps = [
                {"iteration": s.iteration, "action": s.action, "observation": s.observation}
                for s in transcript.history
                if "correct" in s.action.lower() or "fix" in s.action.lower()
            ]
            if correction_steps:
                new_corrections.append({"session_id": sid, "corrections": correction_steps})

        # Merge preferences (new keys from transcript preferences — none in raw transcript,
        # but keep dict merge pattern for future extensibility)
        new_preferences = dict(topics.user_preferences)

        return SessionMemory(
            successful_patterns=new_patterns,
            user_preferences=new_preferences,
            query_corrections=new_corrections,
        )

    # ------------------------------------------------------------------
    # StagingTransactionWriter — atomic topic write (Q3=B, Q2=A staging)
    # ------------------------------------------------------------------

    async def _write_topics_atomic(self, topics: SessionMemory) -> None:
        """Atomically write the 3 topic JSON files using a staging directory.

        Pattern:
        1. Wipe stale .staging/ (if exists from prior crash)
        2. Create .staging/
        3. Write all 3 JSON files to .staging/
        4. Rename each .staging/{file} → topics/{file}
        5. Cleanup: remove .staging/
        """
        # Step 1 + 2: wipe stale staging then create fresh
        await _rmdir_tree(self._staging_dir)
        await _mkdir(self._staging_dir)

        try:
            # Step 3: write all 3 to staging
            patterns_path = self._staging_dir / "successful_patterns.json"
            corrections_path = self._staging_dir / "query_corrections.json"
            preferences_path = self._staging_dir / "user_preferences.json"

            await _write_text(patterns_path, json.dumps(topics.successful_patterns, indent=2, default=str))
            await _write_text(corrections_path, json.dumps(topics.query_corrections, indent=2, default=str))
            await _write_text(preferences_path, json.dumps(topics.user_preferences, indent=2, default=str))

            # Step 4: atomic rename all 3
            await _replace_file(patterns_path, self._topics_dir / "successful_patterns.json")
            await _replace_file(corrections_path, self._topics_dir / "query_corrections.json")
            await _replace_file(preferences_path, self._topics_dir / "user_preferences.json")

        finally:
            # Step 5: cleanup staging dir regardless of success/failure
            await _rmdir_tree(self._staging_dir)

        _log_topics_written(
            patterns=len(topics.successful_patterns),
            corrections=len(topics.query_corrections),
        )

    # ------------------------------------------------------------------
    # MEMORY.md append (NFR-03)
    # ------------------------------------------------------------------

    async def _append_memory_md(self, session_id: str) -> None:
        """Append a one-line entry to MEMORY.md for a consolidated session."""
        import datetime
        entry = (
            f"- {datetime.datetime.utcnow().isoformat()}Z "
            f"consolidated session `{session_id}`\n"
        )
        existing = await _read_text(self._memory_md)
        await _write_text(self._memory_md, existing + entry)
        _log_memory_md_appended(session_id)
