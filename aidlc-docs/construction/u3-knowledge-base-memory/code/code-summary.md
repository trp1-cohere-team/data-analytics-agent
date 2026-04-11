# U3 Code Summary — Knowledge Base & Memory System

**Unit**: U3 — Knowledge Base & Memory  
**Status**: Complete  
**Date**: 2026-04-11

---

## Generated Files

| File | Description | Lines |
|---|---|---|
| `agent/models.py` | Added `SessionTranscript` model to Memory section | +6 |
| `agent/config.py` | Added `memory_delete_after_consolidation` setting | +2 |
| `agent/kb/__init__.py` | Package marker; exports `KnowledgeBase` | 4 |
| `agent/kb/knowledge_base.py` | KnowledgeBase + all internal components | ~305 |
| `agent/memory/__init__.py` | Package marker; exports `MemoryManager` | 4 |
| `agent/memory/manager.py` | MemoryManager + all internal components | ~270 |
| `tests/unit/strategies.py` | Added `session_transcripts()`, `session_memory_objects()`, `trace_steps()`, U3 `INVARIANT_SETTINGS` | +80 |
| `tests/unit/test_knowledge_base.py` | Unit tests + PBT-U3-01/02/03 | ~280 |
| `tests/unit/test_memory_manager.py` | Unit tests + PBT-U3-04/05/06 | ~290 |

---

## Internal Components

### `agent/kb/knowledge_base.py`

| Component | Pattern | Purpose |
|---|---|---|
| `_read_text`, `_write_text`, `_replace_file`, `_mkdir`, `_glob_md`, `_file_exists` | AsyncFileIOWrapper (NFR Q1=A) | Non-blocking disk I/O via `asyncio.to_thread` |
| `_validate_filename` | FilenameGuard (SEC-U3-02) | Regex `^[\w\-. ]+\.md$`; rejects path traversal |
| `_log_documents_loaded`, `_log_document_injected`, etc. | StructuredMemoryLogger | Structured `extra={}` log entries; no file content logged |
| `KnowledgeBase.__init__` | SubdirCache + CorrectionsStore | Initializes `_cache: dict`, `_corrections: list`, instance `asyncio.Lock` |
| `_ensure_kb_structure` | KB-09 / Q9=D | Creates 4 subdirs; seeds `CHANGELOG.md` placeholder |
| `load_documents(subdir)` | HybridTTLCache (Q1=D) | Returns cache if age < `refresh_interval_s`; reloads otherwise; skips `CHANGELOG.md` |
| `inject_document(subdir, filename, content)` | FilenameGuard + TokenGate + CacheInvalidation | Validates filename → 4k token check → write → CHANGELOG append → `_cache.pop` |
| `append_correction(entry)` | AtomicCorrectionsAppend (Q3=C, Q4=A) | Lock → write `.tmp` → rename → update in-memory mirror |
| `get_corrections()` | DefensiveCopy | Returns `list(self._corrections)` (synchronous) |
| `_load_corrections_from_disk()` | CorruptEntryTolerance (DC-01) | Skips individual bad entries; logs warning; returns valid entries |

### `agent/memory/manager.py`

| Component | Pattern | Purpose |
|---|---|---|
| `_read_text`, `_write_text`, `_replace_file`, `_mkdir`, `_glob_json`, `_file_exists`, `_unlink`, `_rmdir_tree` | AsyncFileIOWrapper (NFR Q1=A) | Non-blocking disk I/O via `asyncio.to_thread` |
| `_log_session_saved`, `_log_topics_written`, etc. | StructuredMemoryLogger | Structured `extra={}` log entries; no session content logged |
| `_get_session_lock(session_id)` | InstanceScopedLockRegistry (Q2=B) | `dict[str, asyncio.Lock]` guarded by `_registry_lock` |
| `save_session(session_id, history, summary)` | WriteOnce (Q5=A) + PerSessionLock (Q2=B) | Checks existence → skips if found; writes `SessionTranscript` JSON |
| `load_session(session_id)` | FileRead | Returns `SessionTranscript | None` |
| `get_topics()` | TopicLoader | Reads 3 JSON files; missing files return empty defaults |
| `_run_autodream()` | BackgroundLoop (Q7=B) | `asyncio.ensure_future` at `initialise()`; polls every 5 min |
| `_autodream_cycle()` | StaleSessionScan (Q8=C) | Finds sessions older than `max_age_days`; merges; writes; logs; optionally deletes |
| `_merge_session_into_topics(transcript, topics)` | AdditiveMerge (MM-03) | Dedup by `session_id`; no removal; `user_preferences` dict merge |
| `_write_topics_atomic(topics)` | StagingTransactionWriter (Q3=B, Q2=A) | Wipe `.staging/` → write 3 files → rename all → cleanup in `finally` |
| `_append_memory_md(session_id)` | NFR-03 AppendOnly | Appends one-line entry to `MEMORY.md` |

---

## Design Decisions Implemented

| Decision | Code Location | Description |
|---|---|---|
| Q1=D: Hybrid TTL cache | `load_documents()` | Per-subdir cache with `refresh_interval_s` invalidation |
| Q2=B: 4k token budget | `inject_document()` | `len(content) // 4 > 4_000` raises `ValueError` |
| Q3=C: Atomic corrections swap | `append_correction()` | Write `.tmp` → `replace()` |
| Q4=A: In-memory mirror | `append_correction()` | `self._corrections.append(entry)` after disk succeeds |
| Q5=A: Write-once sessions | `save_session()` | `_file_exists()` check; second call returns early |
| Q6=C: Raw trace + summary | `save_session()` | `SessionTranscript(history=history, summary=summary)` |
| Q7=B: autoDream background | `_run_autodream()` | `asyncio.ensure_future` in `initialise()` |
| Q8=C: Stale threshold | `_autodream_cycle()` | `time.time() - max_age_days * 86_400` |
| Q9=D: KB subdir auto-init | `_ensure_kb_structure()` | Creates 4 subdirs + CHANGELOG.md seeds |
| NFR Q1=A: asyncio.to_thread | All `_read_text` etc. helpers | Non-blocking event loop for disk I/O |
| NFR Q2=A: Staging directory | `_write_topics_atomic()` | `.staging/` for StagingTransactionWriter |
| NFR Q3=B: Instance lock | `KnowledgeBase._corrections_lock` + `MemoryManager._session_locks` | Better test isolation, no global state |

---

## PBT Properties

| ID | File | Description | Examples |
|---|---|---|---|
| PBT-U3-01 | `test_knowledge_base.py` | `CorrectionEntry` round-trip (model_dump → reconstruct) | 200 |
| PBT-U3-02 | `test_knowledge_base.py` | N appends → `len(get_corrections()) == N` (tmp dir) | 100 |
| PBT-U3-03 | `test_knowledge_base.py` | Token gate: >4k chars always raises, ≤4k always succeeds | 150 |
| PBT-U3-04 | `test_memory_manager.py` | Write-once: same session_id × N → exactly 1 file | 100 |
| PBT-U3-05 | `test_memory_manager.py` | Topic merge idempotency: merging twice == merging once | 150 |
| PBT-U3-06 | `test_memory_manager.py` | `SessionMemory` round-trip (write_topics_atomic → get_topics) | 200 |

---

## Security Compliance

| Rule | Status | Implementation |
|---|---|---|
| SEC-U3-01: No content in logs | Compliant | All `_log_*` helpers use metadata fields only; content never logged |
| SEC-U3-02: FilenameGuard | Compliant | `_validate_filename()` regex `^[\w\-. ]+\.md$` + `..` check on every `inject_document` call |

---

## Dependencies (U5 required)

| Dependency | Used for |
|---|---|
| `agent.models.CorrectionEntry` | Corrections store type |
| `agent.models.KBDocument` | Document loading result type |
| `agent.models.SessionMemory` | Topic output type |
| `agent.models.SessionTranscript` | Session persistence type |
| `agent.models.TraceStep` | History in SessionTranscript |
| `agent.config.settings` | `kb_dir`, `layer2_refresh_interval_s`, `memory_dir`, `memory_max_age_days`, `memory_delete_after_consolidation` |
