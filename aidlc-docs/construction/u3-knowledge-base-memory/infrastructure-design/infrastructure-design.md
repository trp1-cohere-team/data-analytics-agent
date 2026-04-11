# Infrastructure Design
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11

---

## Infrastructure Category Assessment

| Category | Status | Justification |
|---|---|---|
| Deployment Environment | N/A | U3 is an in-process library; deploys as part of U1's FastAPI process — no separate deployment unit |
| Compute Infrastructure | N/A | Runs inside U1's process; compute sizing is a U1 concern |
| Storage Infrastructure | **Local file system** | Two owned directories: `kb/` (knowledge base) and `agent/memory/` (session transcripts + topic store). Both are local to the process host. No cloud storage, no DB. |
| Messaging Infrastructure | N/A | autoDream background task uses `asyncio.ensure_future` — pure in-process scheduling, not a message queue |
| Networking Infrastructure | N/A | Zero network calls — U3 is file I/O only. No HTTP, no MCP Toolbox, no OpenRouter. |
| Monitoring Infrastructure | N/A | ObservabilityEmitter uses Python stdlib `logging`; log aggregation is an operational concern outside project scope |
| Shared Infrastructure | N/A | `kb/` and `agent/memory/` are exclusively owned by U3. No other unit writes to these paths. U1 reads from them via KnowledgeBase/MemoryManager APIs only. |

---

## Summary

U3 has **no standalone infrastructure requirements** beyond two local directories. It is an async in-process library that:

1. Runs inside U1's FastAPI server process (single-process deployment)
2. Reads and writes to `kb/` (knowledge base documents + corrections log)
3. Reads and writes to `agent/memory/` (session transcripts + topic store + MEMORY.md index)
4. Uses only Python stdlib — no external services, no network, no cloud

Both directories are owned by the process user running uvicorn. They must exist (or be creatable) on the local file system. `KnowledgeBase.__init__` and `MemoryManager.__init__` auto-create all required subdirectories on first run.

---

## Storage Layout

```
{workspace_root}/
  kb/                           ← KnowledgeBase root (KB_DIR config)
    architecture/
      CHANGELOG.md              (auto-seeded at init)
      *.md                      (injected via inject_document)
    domain/
      CHANGELOG.md
      *.md
    evaluation/
      CHANGELOG.md
      *.md
    corrections/
      CHANGELOG.md
      corrections.json          (JSON array, atomic-swap append)

  agent/
    memory/                     ← MemoryManager root (MEMORY_DIR config)
      MEMORY.md                 (index — auto-created at init)
      sessions/
        {session_id}.json       (SessionTranscript — write-once)
      topics/
        successful_patterns.json
        user_preferences.json
        query_corrections.json
        .staging/               (transient — exists only during autoDream write)
```

---

## Environment Variables

All sourced from `agent/config.py` / `.env`:

| Variable | Default | Used By |
|---|---|---|
| `KB_DIR` | `kb` | KnowledgeBase root path |
| `MEMORY_DIR` | `agent/memory` | MemoryManager root path |
| `LAYER2_REFRESH_INTERVAL_S` | `60` | SubdirCache TTL (seconds) |
| `MEMORY_MAX_AGE_DAYS` | `7` | autoDream stale session threshold |
| `MEMORY_DELETE_AFTER_CONSOLIDATION` | `True` | Session file retention after autoDream |

No new environment variables introduced by U3 beyond what is already in `.env.example`.

---

## Files Produced by U3

```
agent/
  kb/
    knowledge_base.py       ← KnowledgeBase + all internal components
  memory/
    manager.py              ← MemoryManager + all internal components
    MEMORY.md               ← auto-created at first MemoryManager init
    sessions/               ← auto-created at first MemoryManager init
    topics/                 ← auto-created at first MemoryManager init
tests/
  unit/
    test_knowledge_base.py  ← KnowledgeBase unit tests + PBT-U3-01/02/03
    test_memory_manager.py  ← MemoryManager unit tests + PBT-U3-04/05/06
```
