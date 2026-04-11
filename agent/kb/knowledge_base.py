"""Knowledge Base — file-system read/write for KB documents and corrections log.

Design decisions:
  - Q1=D: Hybrid cache — eager load with per-subdir TTL refresh interval
  - Q2=B: 4,000 token budget per injected document (injection test gate)
  - Q3=C: corrections.json stored as JSON array with atomic .tmp→rename swap
  - Q4=A: in-memory corrections mirror updated synchronously with disk write
  - Q9=D: kb/ subdirectories auto-created with placeholder CHANGELOG.md at init
  - NFR Q1=A: all disk I/O wrapped in asyncio.to_thread (non-blocking event loop)
  - NFR Q3=B: instance-level asyncio.Lock for corrections (better test isolation)
  - SEC-U3-02: FilenameGuard (regex) prevents path traversal in inject_document
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.models import CorrectionEntry, KBDocument

_logger = logging.getLogger("agent.kb")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SUBDIRS = frozenset({"architecture", "domain", "evaluation", "corrections"})
_MAX_TOKENS = 4_000           # Q2=B: injection test token budget
_SAFE_FILENAME_RE = re.compile(r"^[\w\-. ]+\.md$")

_CHANGELOG_HEADER = (
    "# CHANGELOG\n\n## {subdir} Knowledge Base\n\n"
    "Append-only log of injected documents.\n"
)

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


async def _glob_md(path: Path) -> list[Path]:
    return await asyncio.to_thread(lambda: sorted(path.glob("*.md")))


async def _file_exists(path: Path) -> bool:
    return await asyncio.to_thread(path.exists)

# ---------------------------------------------------------------------------
# FilenameGuard — Pattern 3 / SEC-U3-02
# ---------------------------------------------------------------------------

def _validate_filename(filename: str) -> None:
    """Raise ValueError on unsafe filenames (path traversal, non-md, etc.)."""
    if ".." in filename:
        raise ValueError(f"Path traversal detected in filename: {filename!r}")
    if not _SAFE_FILENAME_RE.match(filename):
        raise ValueError(
            f"Unsafe filename {filename!r}. "
            "Must match ^[\\w\\-. ]+\\.md$ (alphanumeric, dash, dot, space, .md only)."
        )

# ---------------------------------------------------------------------------
# StructuredMemoryLogger — Pattern 4 (agent.kb)
# ---------------------------------------------------------------------------

def _log_documents_loaded(subdir: str, doc_count: int, from_cache: bool, elapsed_ms: float) -> None:
    _logger.info("documents_loaded", extra={
        "subdir": subdir, "doc_count": doc_count,
        "from_cache": from_cache, "elapsed_ms": round(elapsed_ms, 1),
    })

def _log_document_injected(subdir: str, filename: str, token_estimate: int) -> None:
    _logger.info("document_injected", extra={
        "subdir": subdir, "filename": filename, "token_estimate": token_estimate,
    })

def _log_correction_appended(entry_id: str, failure_type: str, total_count: int) -> None:
    _logger.info("correction_appended", extra={
        "entry_id": entry_id, "failure_type": failure_type, "total_count": total_count,
    })

def _log_corrections_loaded(entry_count: int, skipped_corrupt: int) -> None:
    _logger.info("corrections_loaded", extra={
        "entry_count": entry_count, "skipped_corrupt": skipped_corrupt,
    })

def _log_corrupt_entry_skipped(index: int, error: str) -> None:
    _logger.warning("correction_corrupt_skipped", extra={"index": index, "error": error[:200]})

# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """File-system read/write for KB documents and corrections log.

    FR-08: maintains 4 subdirs (architecture, domain, evaluation, corrections),
    each with an append-only CHANGELOG.md.

    All public methods are async (disk I/O via asyncio.to_thread).
    Exception: get_corrections() is sync — reads from in-memory mirror only.
    """

    def __init__(
        self,
        kb_dir: str | Path | None = None,
        refresh_interval_s: int | None = None,
    ) -> None:
        self._kb_dir = Path(kb_dir or settings.kb_dir)
        self._refresh_interval_s = (
            refresh_interval_s
            if refresh_interval_s is not None
            else settings.layer2_refresh_interval_s
        )
        # SubdirCache: subdir → (docs, loaded_at_monotonic)
        self._cache: dict[str, tuple[list[KBDocument], float]] = {}
        # CorrectionsStore
        self._corrections: list[CorrectionEntry] = []
        self._corrections_lock = asyncio.Lock()   # instance-level (NFR Q3=B)
        self._corrections_path = self._kb_dir / "corrections" / "corrections.json"

    async def initialise(self) -> None:
        """Async init: create directory structure and load corrections from disk.

        Must be called once after construction before using load_documents or
        append_correction. (Separated from __init__ because __init__ cannot be async.)
        """
        await self._ensure_kb_structure()
        self._corrections = await self._load_corrections_from_disk()

    # ------------------------------------------------------------------
    # Private: structure init
    # ------------------------------------------------------------------

    async def _ensure_kb_structure(self) -> None:
        """Create 4 KB subdirs and seed CHANGELOG.md if missing (Q9=D)."""
        for subdir in _VALID_SUBDIRS:
            path = self._kb_dir / subdir
            await _mkdir(path)
            changelog = path / "CHANGELOG.md"
            if not await _file_exists(changelog):
                await _write_text(changelog, _CHANGELOG_HEADER.format(subdir=subdir))

    # ------------------------------------------------------------------
    # Document loading — hybrid cache (Q1=D)
    # ------------------------------------------------------------------

    async def load_documents(self, subdir: str) -> list[KBDocument]:
        """Return KB documents for the given subdir, using hybrid cache.

        Cache hit: returns stored list if age < refresh_interval_s.
        Cache miss/stale: reloads all .md files from disk (excludes CHANGELOG.md).
        """
        if subdir not in _VALID_SUBDIRS:
            raise ValueError(f"Unknown subdir: {subdir!r}. Valid: {_VALID_SUBDIRS}")

        t0 = time.monotonic()
        cached_docs, loaded_at = self._cache.get(subdir, ([], 0.0))

        if cached_docs and (t0 - loaded_at) < self._refresh_interval_s:
            _log_documents_loaded(subdir, len(cached_docs), from_cache=True, elapsed_ms=(time.monotonic() - t0) * 1000)
            return cached_docs

        subdir_path = self._kb_dir / subdir
        files = await _glob_md(subdir_path)
        docs: list[KBDocument] = []
        for md_file in files:
            if md_file.name == "CHANGELOG.md":
                continue   # KB-09: CHANGELOG not served to LLM
            content = await _read_text(md_file)
            docs.append(KBDocument(
                path=str(md_file),
                content=content,
                subdirectory=subdir,
            ))

        self._cache[subdir] = (docs, time.monotonic())
        _log_documents_loaded(subdir, len(docs), from_cache=False, elapsed_ms=(time.monotonic() - t0) * 1000)
        return docs

    # ------------------------------------------------------------------
    # Document injection
    # ------------------------------------------------------------------

    async def inject_document(self, subdir: str, filename: str, content: str) -> None:
        """Write a markdown document to the KB and append a CHANGELOG entry.

        Raises:
            ValueError: unknown subdir, unsafe filename, or content > 4k tokens.
        """
        if subdir not in _VALID_SUBDIRS:
            raise ValueError(f"Unknown subdir: {subdir!r}")

        _validate_filename(filename)   # SEC-U3-02

        token_estimate = len(content) // 4
        if token_estimate > _MAX_TOKENS:
            raise ValueError(
                f"Document exceeds {_MAX_TOKENS:,} token budget: "
                f"~{token_estimate:,} tokens. Split the document."
            )

        # Validate UTF-8 (raises UnicodeEncodeError if invalid)
        content.encode("utf-8")

        target = self._kb_dir / subdir / filename
        await _write_text(target, content)

        # Append to CHANGELOG.md (KB-02: append-only)
        changelog = self._kb_dir / subdir / "CHANGELOG.md"
        import datetime
        entry = (
            f"\n## {datetime.datetime.utcnow().isoformat()}Z\n"
            f"- Injected: `{filename}` (~{token_estimate:,} tokens)\n"
        )
        existing = await _read_text(changelog)
        await _write_text(changelog, existing + entry)

        # Invalidate cache for this subdir (KB-04)
        self._cache.pop(subdir, None)
        _log_document_injected(subdir, filename, token_estimate)

    # ------------------------------------------------------------------
    # Corrections — atomic append with in-memory mirror
    # ------------------------------------------------------------------

    async def append_correction(self, entry: CorrectionEntry) -> None:
        """Append a correction entry to corrections.json and the in-memory mirror.

        Atomic write (Q3=C): write .tmp file then rename.
        Dual write (Q4=A): update self._corrections after disk succeeds.
        Serialized (NFR Q1=D): acquires self._corrections_lock.
        """
        async with self._corrections_lock:
            all_entries = list(self._corrections) + [entry]
            serialised = json.dumps(
                [e.model_dump() for e in all_entries],
                indent=2,
                default=str,
            )
            tmp_path = self._corrections_path.with_suffix(".json.tmp")
            await _write_text(tmp_path, serialised)
            await _replace_file(tmp_path, self._corrections_path)
            self._corrections.append(entry)   # update mirror only after disk succeeds

        _log_correction_appended(entry.id, entry.failure_type, len(self._corrections))

    def get_corrections(self) -> list[CorrectionEntry]:
        """Return a defensive copy of the in-memory corrections list (synchronous)."""
        return list(self._corrections)

    async def _load_corrections_from_disk(self) -> list[CorrectionEntry]:
        """Read corrections.json and parse into CorrectionEntry list.

        Tolerates individual corrupt entries (DC-01): logs warning, skips entry.
        """
        if not await _file_exists(self._corrections_path):
            _log_corrections_loaded(0, 0)
            return []

        raw = await _read_text(self._corrections_path)
        raw = raw.strip()
        if not raw:
            _log_corrections_loaded(0, 0)
            return []

        try:
            data: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError as exc:
            _logger.error("corrections_json_parse_failed", extra={"error": str(exc)})
            return []

        entries: list[CorrectionEntry] = []
        skipped = 0
        for i, item in enumerate(data):
            try:
                entries.append(CorrectionEntry(**item))
            except Exception as exc:  # noqa: BLE001
                _log_corrupt_entry_skipped(i, str(exc))
                skipped += 1

        _log_corrections_loaded(len(entries), skipped)
        return entries
