"""Unit tests for agent/context/manager.py."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.context.manager import ContextManager
from agent.models import (
    CorrectionEntry,
    DomainContext,
    KBDocument,
    SchemaContext,
    SessionMemory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(
    kb=None, memory=None, schema_introspector=None, tmp_path=None
) -> ContextManager:
    kb = kb or MagicMock()
    kb.load_documents = AsyncMock(return_value=[])
    kb.get_corrections = MagicMock(return_value=[])

    memory = memory or MagicMock()
    memory.get_topics = AsyncMock(return_value=SessionMemory())

    introspector = schema_introspector or MagicMock()
    introspector.introspect_all = AsyncMock(return_value=SchemaContext(databases={}))

    import tempfile
    from pathlib import Path
    kb_dir = tmp_path or Path(tempfile.mkdtemp())

    mgr = ContextManager(
        kb=kb, memory=memory, schema_introspector=introspector,
        kb_dir=kb_dir, refresh_interval_s=999,
    )
    return mgr


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# startup_load
# ---------------------------------------------------------------------------

class TestStartupLoad:
    def test_calls_schema_introspector(self):
        introspector = MagicMock()
        introspector.introspect_all = AsyncMock(return_value=SchemaContext(databases={}))
        mgr = _make_manager(schema_introspector=introspector)
        _run(mgr.startup_load())
        introspector.introspect_all.assert_called_once()

    def test_loads_layer2_documents(self):
        doc = KBDocument(path="doc.md", content="# Hello", subdirectory="domain")
        kb = MagicMock()
        kb.load_documents = AsyncMock(side_effect=lambda subdir: [doc] if subdir == "domain" else [])
        kb.get_corrections = MagicMock(return_value=[])
        mgr = _make_manager(kb=kb)
        _run(mgr.startup_load())
        assert mgr._domain_ctx is not None
        assert any(d.path == "doc.md" for d in mgr._domain_ctx.documents)

    def test_handles_introspector_failure_gracefully(self):
        introspector = MagicMock()
        introspector.introspect_all = AsyncMock(side_effect=RuntimeError("MCP down"))
        mgr = _make_manager(schema_introspector=introspector)
        _run(mgr.startup_load())  # must not raise
        assert mgr._schema_ctx is not None
        assert mgr._schema_ctx.databases == {}


# ---------------------------------------------------------------------------
# get_context_bundle
# ---------------------------------------------------------------------------

class TestGetContextBundle:
    def test_returns_all_three_layers(self):
        mgr = _make_manager()
        _run(mgr.startup_load())
        bundle = _run(mgr.get_context_bundle("sess-1"))
        assert bundle.schema_ctx is not None
        assert bundle.domain_ctx is not None
        assert bundle.corrections_ctx is not None

    def test_layer3_includes_corrections(self):
        kb = MagicMock()
        kb.load_documents = AsyncMock(return_value=[])
        entry = MagicMock(spec=CorrectionEntry)
        kb.get_corrections = MagicMock(return_value=[entry])
        memory = MagicMock()
        memory.get_topics = AsyncMock(return_value=SessionMemory())
        mgr = _make_manager(kb=kb, memory=memory)
        _run(mgr.startup_load())
        bundle = _run(mgr.get_context_bundle("sess-1"))
        assert len(bundle.corrections_ctx.corrections) == 1

    def test_layer3_always_fresh(self):
        call_count = 0
        kb = MagicMock()
        kb.load_documents = AsyncMock(return_value=[])

        def _get_corrections():
            nonlocal call_count
            call_count += 1
            return []

        kb.get_corrections = _get_corrections
        memory = MagicMock()
        memory.get_topics = AsyncMock(return_value=SessionMemory())
        mgr = _make_manager(kb=kb, memory=memory)
        _run(mgr.startup_load())
        _run(mgr.get_context_bundle("sess-1"))
        _run(mgr.get_context_bundle("sess-2"))
        assert call_count >= 2  # loaded fresh each time


# ---------------------------------------------------------------------------
# Layer 2 cache and invalidation
# ---------------------------------------------------------------------------

class TestLayer2Cache:
    def test_cache_hit_returns_same_docs(self):
        doc = KBDocument(path="doc.md", content="# Doc", subdirectory="domain")
        kb = MagicMock()
        load_count = [0]

        async def _load(subdir):
            load_count[0] += 1
            return [doc] if subdir == "domain" else []

        kb.load_documents = _load
        kb.get_corrections = MagicMock(return_value=[])
        memory = MagicMock()
        memory.get_topics = AsyncMock(return_value=SessionMemory())
        mgr = _make_manager(kb=kb, memory=memory, refresh_interval_s=999)
        _run(mgr.startup_load())
        initial_count = load_count[0]
        _run(mgr.get_context_bundle("sess-1"))
        # Layer 2 should not reload (no file mtime changes, high refresh_interval)
        assert load_count[0] == initial_count  # no extra loads

    def test_invalidate_triggers_reload(self):
        kb = MagicMock()
        load_count = [0]

        async def _load(subdir):
            load_count[0] += 1
            return []

        kb.load_documents = _load
        kb.get_corrections = MagicMock(return_value=[])
        memory = MagicMock()
        memory.get_topics = AsyncMock(return_value=SessionMemory())
        mgr = _make_manager(kb=kb, memory=memory)
        _run(mgr.startup_load())
        count_before = load_count[0]
        _run(mgr.invalidate_layer2_cache())
        assert load_count[0] > count_before
