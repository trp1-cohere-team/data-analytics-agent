# Deployment Architecture
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11

---

## Runtime Position

```
OS Process: uvicorn (FastAPI)              port 8000
  └── agent/api/app.py  (U1 — AgentAPI)
        └── agent/orchestrator/react_loop.py  (U1 — Orchestrator)
              ├── KnowledgeBase(kb_dir)
              │     ├── load_documents("architecture")  ──→ kb/architecture/*.md
              │     ├── load_documents("domain")        ──→ kb/domain/*.md
              │     ├── load_documents("corrections")   ──→ kb/corrections/*.md
              │     └── append_correction(entry)        ──→ kb/corrections/corrections.json
              │
              └── MemoryManager(memory_dir)
                    ├── save_session(session_id, ...)   ──→ agent/memory/sessions/{id}.json
                    ├── get_topics()                    ──→ agent/memory/topics/*.json
                    └── [background] _run_autoDream()   ──→ agent/memory/topics/ (staging)
                                                             agent/memory/MEMORY.md

Local File System (same host as uvicorn)
  ├── kb/                  (KnowledgeBase root)
  └── agent/memory/        (MemoryManager root)
```

---

## Lifecycle

| Event | Action |
|---|---|
| Agent startup (`uvicorn` start) | U1 instantiates `KnowledgeBase` and `MemoryManager`; both auto-create directories; MemoryManager schedules autoDream background task |
| First `load_documents` call | Cache miss → disk read via `asyncio.to_thread` → cache populated |
| Subsequent `load_documents` within TTL | Cache hit → returns in-memory list, no disk I/O |
| `inject_document` | Filename guard → token check → disk write → CHANGELOG append → cache invalidated |
| Per query end | `save_session` called by U1 Orchestrator → existence check → write SessionTranscript JSON |
| autoDream task (background) | Scans sessions older than 7 days → staging write → atomic rename → MEMORY.md append → optional session delete |
| Agent shutdown | No explicit cleanup needed — file handles are closed after each operation; staging dir cleaned in `finally` block |

---

## Thread Pool Usage

All disk I/O uses `asyncio.to_thread()`, which submits to Python's default `ThreadPoolExecutor`:

| Operation | Worker Threads Used |
|---|---|
| `load_documents` (cache miss) | 1 thread per glob + N threads for N file reads (batched with `asyncio.gather`) |
| `append_correction` | 1 thread for write + 1 for replace (sequential inside lock) |
| `save_session` | 1 thread for exists check + 1 for write |
| `_run_autoDream` | Multiple threads for session reads + 3 threads for staging writes + 3 for renames |

Default pool size: `min(32, os.cpu_count() + 4)`. At single-agent scale this is never saturated.

---

## Environment Variables

All sourced from `agent/config.py` / `.env`:

| Variable | Default | Used By |
|---|---|---|
| `KB_DIR` | `kb` | `KnowledgeBase(kb_dir=settings.kb_dir)` |
| `MEMORY_DIR` | `agent/memory` | `MemoryManager(memory_dir=settings.memory_dir)` |
| `LAYER2_REFRESH_INTERVAL_S` | `60` | SubdirCache TTL |
| `MEMORY_MAX_AGE_DAYS` | `7` | autoDream stale threshold |
| `MEMORY_DELETE_AFTER_CONSOLIDATION` | `True` | Session deletion post-consolidation |

No new environment variables introduced beyond what is already in `.env.example`.
