"""ContextManager — three-layer context assembly for The Oracle Forge agent.

Design decisions:
  - Layer 1 (schema): loaded once at startup via SchemaIntrospector; permanent cache
  - Layer 2 (domain KB): mtime-based staleness check; reloads all-or-nothing (Q6=A)
  - Layer 3 (corrections): always fresh per session — never cached
  - Q7=B: corrections formatted as markdown bullets for LLM prompt
  - NFR Q1=A: all disk I/O via asyncio.to_thread (delegated to KnowledgeBase/MemoryManager)
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.models import (
    ContextBundle,
    CorrectionsContext,
    DomainContext,
    SchemaContext,
)

_logger = logging.getLogger("agent.context")

# ---------------------------------------------------------------------------
# Structured log helpers (SEC-U1-01)
# ---------------------------------------------------------------------------

def _log_context_assembled(
    session_id: str, layer2_doc_count: int, correction_count: int, elapsed_ms: float
) -> None:
    _logger.info("context_assembled", extra={
        "session_id": session_id,
        "layer2_doc_count": layer2_doc_count,
        "correction_count": correction_count,
        "elapsed_ms": round(elapsed_ms, 1),
    })


def _log_layer2_refreshed(doc_count: int) -> None:
    _logger.info("layer2_refreshed", extra={"doc_count": doc_count})


def _log_layer2_stale(changed_file: str) -> None:
    _logger.info("layer2_stale_detected", extra={"changed_file": changed_file})

# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------

class ContextManager:
    """Assembles the three context layers for each agent session.

    Layer 1 — schema: permanent in-memory cache (loaded once at startup)
    Layer 2 — domain KB: mtime-refreshed background task every layer2_refresh_interval_s
    Layer 3 — corrections: always fresh per session (no caching)
    """

    def __init__(
        self,
        kb: Any,                    # KnowledgeBase
        memory: Any,                # MemoryManager
        schema_introspector: Any,   # SchemaIntrospector
        kb_dir: str | Path | None = None,
        refresh_interval_s: int | None = None,
    ) -> None:
        self._kb = kb
        self._memory = memory
        self._schema_introspector = schema_introspector
        self._kb_dir = Path(kb_dir or settings.kb_dir)
        self._refresh_interval_s = (
            refresh_interval_s
            if refresh_interval_s is not None
            else settings.layer2_refresh_interval_s
        )

        # Layer 1 — permanent
        self._schema_ctx: SchemaContext | None = None

        # Layer 2 — mtime cache
        self._domain_ctx: DomainContext | None = None
        self._layer2_loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def startup_load(self) -> None:
        """Load Layer 1 (schema) and Layer 2 (domain KB) at server startup."""
        # Layer 1
        try:
            self._schema_ctx = await self._schema_introspector.introspect_all()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("schema_introspect_failed", extra={"error": str(exc)[:200]})
            self._schema_ctx = SchemaContext(databases={})

        # Layer 2
        await self._load_layer2()

    # ------------------------------------------------------------------
    # Per-session context assembly
    # ------------------------------------------------------------------

    async def get_context_bundle(self, session_id: str) -> ContextBundle:
        """Assemble all three layers into a ContextBundle for this session."""
        t0 = time.monotonic()

        # Layer 1 — always from permanent cache
        schema_ctx = self._schema_ctx or SchemaContext(databases={})

        # Layer 2 — reload if any file is newer than last load (Q6=A)
        await self._check_and_refresh_layer2()
        domain_ctx = self._domain_ctx or DomainContext(documents=[])

        # Layer 3 — always fresh
        corrections_ctx = await self._load_layer3()

        elapsed = (time.monotonic() - t0) * 1000
        _log_context_assembled(
            session_id=session_id,
            layer2_doc_count=len(domain_ctx.documents),
            correction_count=len(corrections_ctx.corrections),
            elapsed_ms=elapsed,
        )

        return ContextBundle(
            schema_ctx=schema_ctx,
            domain_ctx=domain_ctx,
            corrections_ctx=corrections_ctx,
        )

    # ------------------------------------------------------------------
    # Layer 2 — mtime-based reload (Q6=A)
    # ------------------------------------------------------------------

    async def _check_and_refresh_layer2(self) -> None:
        """Reload Layer 2 if any .md file is newer than _layer2_loaded_at."""
        if self._layer2_loaded_at == 0.0:
            await self._load_layer2()
            return

        changed = await asyncio.to_thread(self._find_changed_file)
        if changed:
            _log_layer2_stale(changed)
            await self._load_layer2()

    def _find_changed_file(self) -> str:
        """Scan KB subdirs for any .md file newer than _layer2_loaded_at. Returns path or ''."""
        for subdir in ("architecture", "domain", "evaluation"):
            subdir_path = self._kb_dir / subdir
            if not subdir_path.exists():
                continue
            for md_file in subdir_path.glob("*.md"):
                if md_file.stat().st_mtime > self._layer2_loaded_at:
                    return str(md_file)
        return ""

    async def _load_layer2(self) -> None:
        """Load all domain KB documents into Layer 2 cache."""
        import datetime
        docs = []
        for subdir in ("architecture", "domain", "evaluation"):
            try:
                subdir_docs = await self._kb.load_documents(subdir)
                docs.extend(subdir_docs)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("layer2_subdir_load_failed", extra={
                    "subdir": subdir, "error": str(exc)[:200],
                })
        self._domain_ctx = DomainContext(
            documents=docs,
            loaded_at=datetime.datetime.utcnow(),
        )
        self._layer2_loaded_at = time.monotonic()
        _log_layer2_refreshed(len(docs))

    # ------------------------------------------------------------------
    # Layer 3 — always fresh
    # ------------------------------------------------------------------

    async def _load_layer3(self) -> CorrectionsContext:
        """Load corrections + session memory fresh for this session."""
        corrections = self._kb.get_corrections()[-settings.corrections_limit:]
        try:
            session_memory = await self._memory.get_topics()
            memory_dict = session_memory.model_dump()
        except Exception:  # noqa: BLE001
            memory_dict = {}
        return CorrectionsContext(
            corrections=corrections,
            session_memory=memory_dict,
        )

    # ------------------------------------------------------------------
    # Background refresh loop — Pattern 7 (Q8=B)
    # ------------------------------------------------------------------

    async def _refresh_layer2_loop(self) -> None:
        """Infinite background task: check Layer 2 staleness every refresh_interval_s."""
        while True:
            await asyncio.sleep(self._refresh_interval_s)
            try:
                await self._check_and_refresh_layer2()
            except Exception as exc:  # noqa: BLE001
                _logger.error("layer2_refresh_error", extra={"error": str(exc)[:200]})

    # ------------------------------------------------------------------
    # Force-reload (for tests)
    # ------------------------------------------------------------------

    async def invalidate_layer2_cache(self) -> None:
        """Force Layer 2 reload on next get_context_bundle() call."""
        self._layer2_loaded_at = 0.0
        await self._load_layer2()
