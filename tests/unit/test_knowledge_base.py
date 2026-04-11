"""Unit tests for agent/kb/knowledge_base.py.

Covers:
  - KnowledgeBase._ensure_kb_structure (4 subdirs + CHANGELOG seeds)
  - load_documents: empty subdir, skip CHANGELOG, cache hit/miss, invalidation after inject
  - inject_document: write, CHANGELOG append, raises on bad filename, raises >4k tokens
  - append_correction: count increment, dual write, concurrent lock safety
  - get_corrections: defensive copy
  - _load_corrections_from_disk: corrupt entry tolerance
  - PBT-U3-01: CorrectionEntry round-trip (200 examples)
  - PBT-U3-02: Append-only count invariant (100 examples, tmp dir)
  - PBT-U3-03: Injection token gate — >4k always raises; ≤4k always succeeds (150 examples)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from agent.kb.knowledge_base import KnowledgeBase, _validate_filename
from agent.models import CorrectionEntry
from tests.unit.strategies import INVARIANT_SETTINGS, correction_entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kb(tmp_path: Path, refresh_interval_s: int = 60) -> KnowledgeBase:
    return KnowledgeBase(kb_dir=tmp_path, refresh_interval_s=refresh_interval_s)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _correction(session_id: str | None = None, failure_type: str = "UNKNOWN") -> CorrectionEntry:
    return CorrectionEntry(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        session_id=session_id or str(uuid.uuid4()),
        failure_type=failure_type,
        original_query="SELECT 1",
        corrected_query=None,
        error_message="test error",
        fix_strategy="rule_syntax",
        attempt_number=1,
        success=False,
    )


# ---------------------------------------------------------------------------
# _ensure_kb_structure
# ---------------------------------------------------------------------------

class TestEnsureKBStructure:
    def test_creates_all_four_subdirs(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        for subdir in ("architecture", "domain", "evaluation", "corrections"):
            assert (tmp_path / subdir).is_dir()

    def test_seeds_changelog_in_each_subdir(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        for subdir in ("architecture", "domain", "evaluation", "corrections"):
            changelog = tmp_path / subdir / "CHANGELOG.md"
            assert changelog.exists()
            content = changelog.read_text()
            assert "CHANGELOG" in content

    def test_idempotent_second_call(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        _run(kb.initialise())   # should not raise or duplicate content
        changelog = tmp_path / "architecture" / "CHANGELOG.md"
        text = changelog.read_text()
        assert text.count("# CHANGELOG") == 1


# ---------------------------------------------------------------------------
# load_documents
# ---------------------------------------------------------------------------

class TestLoadDocuments:
    def test_empty_subdir_returns_empty_list(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        docs = _run(kb.load_documents("architecture"))
        assert docs == []

    def test_skips_changelog_md(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        # CHANGELOG.md already seeded; no other .md files
        docs = _run(kb.load_documents("architecture"))
        assert all(d.path.endswith("CHANGELOG.md") is False for d in docs)

    def test_loads_real_document(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        doc_path = tmp_path / "domain" / "test-doc.md"
        doc_path.write_text("# Test\n\nHello world.")
        docs = _run(kb.load_documents("domain"))
        assert len(docs) == 1
        assert docs[0].content == "# Test\n\nHello world."
        assert docs[0].subdirectory == "domain"

    def test_cache_hit_after_first_load(self, tmp_path):
        kb = _kb(tmp_path, refresh_interval_s=60)
        _run(kb.initialise())
        (tmp_path / "domain" / "doc.md").write_text("# Doc")
        docs1 = _run(kb.load_documents("domain"))
        # Add a second doc — should NOT appear (cache hit)
        (tmp_path / "domain" / "doc2.md").write_text("# Doc2")
        docs2 = _run(kb.load_documents("domain"))
        assert len(docs1) == len(docs2)

    def test_cache_miss_after_ttl(self, tmp_path):
        kb = _kb(tmp_path, refresh_interval_s=0)
        _run(kb.initialise())
        (tmp_path / "domain" / "doc.md").write_text("# Doc1")
        docs1 = _run(kb.load_documents("domain"))
        (tmp_path / "domain" / "doc2.md").write_text("# Doc2")
        docs2 = _run(kb.load_documents("domain"))
        assert len(docs2) > len(docs1)

    def test_cache_invalidated_after_inject(self, tmp_path):
        kb = _kb(tmp_path, refresh_interval_s=60)
        _run(kb.initialise())
        docs_before = _run(kb.load_documents("domain"))
        _run(kb.inject_document("domain", "new-doc.md", "# Injected"))
        docs_after = _run(kb.load_documents("domain"))
        assert len(docs_after) > len(docs_before)

    def test_raises_on_unknown_subdir(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        with pytest.raises(ValueError, match="Unknown subdir"):
            _run(kb.load_documents("nonexistent"))


# ---------------------------------------------------------------------------
# inject_document
# ---------------------------------------------------------------------------

class TestInjectDocument:
    def test_writes_file_to_disk(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        _run(kb.inject_document("architecture", "spec.md", "# Spec"))
        assert (tmp_path / "architecture" / "spec.md").exists()
        assert (tmp_path / "architecture" / "spec.md").read_text() == "# Spec"

    def test_appends_to_changelog(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        _run(kb.inject_document("architecture", "spec.md", "# Spec"))
        changelog = (tmp_path / "architecture" / "CHANGELOG.md").read_text()
        assert "spec.md" in changelog

    def test_raises_on_path_traversal(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        with pytest.raises(ValueError, match="traversal"):
            _run(kb.inject_document("architecture", "../evil.md", "x"))

    def test_raises_on_no_md_extension(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        with pytest.raises(ValueError):
            _run(kb.inject_document("architecture", "file.txt", "x"))

    def test_raises_on_token_limit_exceeded(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        # 4k tokens ≈ 16,001+ characters
        big_content = "x" * (4_000 * 4 + 1)
        with pytest.raises(ValueError, match="token budget"):
            _run(kb.inject_document("architecture", "big.md", big_content))

    def test_accepts_exactly_at_token_limit(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        # 4,000 tokens = 16,000 chars exactly
        content = "x" * (4_000 * 4)
        _run(kb.inject_document("architecture", "edge.md", content))
        assert (tmp_path / "architecture" / "edge.md").exists()

    def test_raises_on_unknown_subdir(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        with pytest.raises(ValueError, match="Unknown subdir"):
            _run(kb.inject_document("bogus", "doc.md", "x"))


# ---------------------------------------------------------------------------
# append_correction + get_corrections
# ---------------------------------------------------------------------------

class TestAppendCorrection:
    def test_increments_count(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        assert len(kb.get_corrections()) == 0
        _run(kb.append_correction(_correction()))
        assert len(kb.get_corrections()) == 1
        _run(kb.append_correction(_correction()))
        assert len(kb.get_corrections()) == 2

    def test_dual_write_disk_and_mirror(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        entry = _correction()
        _run(kb.append_correction(entry))
        # Disk
        raw = (tmp_path / "corrections" / "corrections.json").read_text()
        data = json.loads(raw)
        assert len(data) == 1
        assert data[0]["id"] == entry.id
        # Mirror
        assert kb.get_corrections()[0].id == entry.id

    def test_get_corrections_defensive_copy(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        _run(kb.append_correction(_correction()))
        copy1 = kb.get_corrections()
        copy2 = kb.get_corrections()
        assert copy1 is not copy2

    def test_concurrent_appends_are_safe(self, tmp_path):
        """Concurrent appends must not corrupt the JSON file."""
        kb = _kb(tmp_path)

        async def _concurrent():
            await kb.initialise()
            entries = [_correction() for _ in range(10)]
            await asyncio.gather(*[kb.append_correction(e) for e in entries])

        asyncio.get_event_loop().run_until_complete(_concurrent())
        raw = (tmp_path / "corrections" / "corrections.json").read_text()
        data = json.loads(raw)
        assert len(data) == 10


# ---------------------------------------------------------------------------
# _load_corrections_from_disk — corrupt entry tolerance
# ---------------------------------------------------------------------------

class TestLoadCorrectionsFromDisk:
    def test_skips_corrupt_entries(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        good = _correction().model_dump()
        corrupt = {"id": "bad", "garbage": True}
        path = tmp_path / "corrections" / "corrections.json"
        path.write_text(json.dumps([good, corrupt, good]))

        entries = _run(kb._load_corrections_from_disk())
        assert len(entries) == 2  # 2 valid, 1 corrupt skipped

    def test_returns_empty_if_file_missing(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        entries = _run(kb._load_corrections_from_disk())
        assert entries == []

    def test_returns_empty_on_invalid_json(self, tmp_path):
        kb = _kb(tmp_path)
        _run(kb.initialise())
        path = tmp_path / "corrections" / "corrections.json"
        path.write_text("NOT VALID JSON {{{")
        entries = _run(kb._load_corrections_from_disk())
        assert entries == []


# ---------------------------------------------------------------------------
# FilenameGuard unit tests
# ---------------------------------------------------------------------------

class TestValidateFilename:
    @pytest.mark.parametrize("name", [
        "valid-doc.md",
        "valid_doc.md",
        "valid doc.md",
        "v1.2.md",
        "a.md",
    ])
    def test_valid_names_pass(self, name):
        _validate_filename(name)   # must not raise

    @pytest.mark.parametrize("name", [
        "../traversal.md",
        "../../etc/passwd",
        "file.txt",
        "file.md.exe",
        "file",
        "",
        "file\x00name.md",
    ])
    def test_invalid_names_raise(self, name):
        with pytest.raises(ValueError):
            _validate_filename(name)


# ---------------------------------------------------------------------------
# PBT-U3-01: CorrectionEntry round-trip
# ---------------------------------------------------------------------------

@given(entry=correction_entries())
@INVARIANT_SETTINGS["PBT-U3-01"]
def test_pbt_u3_01_correction_entry_roundtrip(entry: CorrectionEntry):
    """PBT-U3-01: CorrectionEntry serialises and deserialises without data loss."""
    data = entry.model_dump()
    reconstructed = CorrectionEntry(**data)
    assert reconstructed.id == entry.id
    assert reconstructed.session_id == entry.session_id
    assert reconstructed.failure_type == entry.failure_type
    assert reconstructed.original_query == entry.original_query
    assert reconstructed.success == entry.success


# ---------------------------------------------------------------------------
# PBT-U3-02: Append-only count invariant
# ---------------------------------------------------------------------------

@given(entries=st.lists(correction_entries(), min_size=1, max_size=20))
@INVARIANT_SETTINGS["PBT-U3-02"]
def test_pbt_u3_02_append_only_count(entries: list[CorrectionEntry]):
    """PBT-U3-02: N appends → len(get_corrections()) == N (append-only invariant)."""
    import tempfile
    from pathlib import Path

    async def _run_test(tmp_path):
        kb = KnowledgeBase(kb_dir=tmp_path, refresh_interval_s=60)
        await kb.initialise()
        for e in entries:
            await kb.append_correction(e)
        return kb.get_corrections()

    with tempfile.TemporaryDirectory() as td:
        result = asyncio.get_event_loop().run_until_complete(_run_test(Path(td)))
    assert len(result) == len(entries)


# ---------------------------------------------------------------------------
# PBT-U3-03: Injection token gate
# ---------------------------------------------------------------------------

@given(
    size=st.integers(min_value=0, max_value=100_000),
)
@INVARIANT_SETTINGS["PBT-U3-03"]
def test_pbt_u3_03_token_gate(size: int):
    """PBT-U3-03: inject_document raises iff content > 4k tokens (> 16,000 chars)."""
    import tempfile
    from pathlib import Path

    content = "a" * size

    async def _run_test(tmp_path):
        kb = KnowledgeBase(kb_dir=tmp_path, refresh_interval_s=60)
        await kb.initialise()
        try:
            await kb.inject_document("architecture", "test.md", content)
            return True
        except ValueError as exc:
            if "token budget" in str(exc):
                return False
            raise

    with tempfile.TemporaryDirectory() as td:
        succeeded = asyncio.get_event_loop().run_until_complete(_run_test(Path(td)))
    if size > 4_000 * 4:  # more than 16,000 chars → more than 4k tokens
        assert not succeeded, f"Expected rejection for size={size} but succeeded"
    else:
        assert succeeded, f"Expected success for size={size} but raised"
