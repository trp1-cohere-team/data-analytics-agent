# NFR Requirements
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11  
**NFR Decisions**: Q1=D (asyncio.Lock), Q2=B (Lock per session_id), Q3=B (full rollback),
Q4=D (configurable delete), Q5=D (all 3 KB PBT), Q6=D (all 3 MM PBT), Q7=D (structured logs)

---

## Concurrency Requirements

### CONC-U3-01 — Corrections Write Serialization
- `append_correction` acquires a module-level `asyncio.Lock` before the read-modify-write cycle.
- Lock scope: `load_from_disk → extend → atomic_write → update_in_memory`.
- Rationale: single-process deployment (Q1=D) — cross-process locking is not needed; `asyncio.Lock` covers all in-process coroutines sharing the same event loop.
- The lock is held for the minimum duration — disk I/O only; no LLM calls inside lock.

### CONC-U3-02 — Session Write Serialization per session_id
- `save_session` acquires a per-session-id `asyncio.Lock` from a `defaultdict(asyncio.Lock)`.
- Prevents the TOCTOU race between the existence check and the file write.
- Locks for different session_ids are independent — no cross-session contention.
- Rationale: Q2=B; duplicate session_id is a caller bug, but the lock makes the behaviour safe rather than undefined.

---

## Reliability Requirements

### REL-U3-01 — autoDream Full Rollback on Failure
- `_run_autoDream` writes all three topic files to a staging directory (`topics/.staging/`) before replacing originals.
- Only after all three staging files are written successfully does the code perform the atomic renames.
- If any staging write fails, the staging directory is cleaned up and originals are untouched.
- Rationale: Q3=B — partial consolidation (e.g., successful_patterns updated but query_corrections not) would produce an inconsistent topic store.

### REL-U3-02 — Configurable Session Retention After Consolidation
- After successful autoDream consolidation, session files older than `memory_max_age_days` are either deleted or archived depending on `memory_delete_after_consolidation` setting.
- `True` (default): delete session files after consolidation — keeps disk bounded.
- `False`: retain all session files forever.
- Deletion only occurs after all three topic file renames succeed — never on partial failure.
- Rationale: Q4=D.

### REL-U3-03 — autoDream Idempotency
- Session deduplication by `session_id` in `_merge_session_into_topics` guarantees that re-processing the same session (e.g., after a partial failure) produces the same output as processing it once.
- Topic files are additive only (KB-08) — idempotency holds even if a session is processed twice.

### REL-U3-04 — Corrupt Entry Tolerance in Corrections Log
- `_load_corrections_from_disk` wraps each `CorrectionEntry(**item)` in a try/except.
- A corrupted entry is logged at WARNING level and skipped — it does not prevent the remaining entries from loading.
- Total loaded count is logged so operators can detect unexpected drops.

---

## Property-Based Testing Requirements (blocking — PBT extension)

### PBT-U3-01 — CorrectionEntry Round-Trip (KnowledgeBase)
- **Invariant**: `CorrectionEntry` serialized to a dict with `model_dump()` and reconstructed with `CorrectionEntry(**data)` produces an object equal to the original.
- Covers: all field types (str, float, int, bool, str|None).
- Settings: 200 examples, 500ms deadline.

### PBT-U3-02 — Append-Only Count Invariant (KnowledgeBase)
- **Invariant**: Starting from an empty corrections log, calling `append_correction` N times (N drawn from 1–50) always results in `len(get_corrections()) == N`.
- Covers: no deduplication, no silent drops, no off-by-one errors in the atomic swap.
- Settings: 100 examples, 2000ms deadline (includes disk I/O on temp dir).

### PBT-U3-03 — Injection Token Gate (KnowledgeBase)
- **Invariant 1**: `inject_document` with `len(content) // 4 > 4000` always raises `ValueError` — no file is created.
- **Invariant 2**: `inject_document` with `len(content) // 4 <= 4000` always succeeds — file exists on disk after the call.
- Covers: boundary at exactly 16,000 characters (= 4,000 tokens) and around it.
- Settings: 150 examples, 1000ms deadline.

### PBT-U3-04 — Write-Once Session Count (MemoryManager)
- **Invariant**: Calling `save_session(session_id, ...)` twice with the same `session_id` never results in more than one session file for that id. The sessions directory count for that id remains 1.
- Covers: the TOCTOU race window and the `asyncio.Lock` per session_id guard.
- Settings: 100 examples, 1000ms deadline.

### PBT-U3-05 — Topic Merge Idempotency (MemoryManager)
- **Invariant**: `_merge_session_into_topics(transcript, topics)` called twice with the same `transcript` produces the same `SessionMemory` as calling it once.
- Covers: deduplication logic in successful_patterns and query_corrections lists.
- Settings: 150 examples, 500ms deadline.

### PBT-U3-06 — SessionMemory Round-Trip (MemoryManager)
- **Invariant**: `SessionMemory` serialized to JSON (via `model_dump_json`) and reloaded produces an object where all list and dict fields are equal.
- Covers: `successful_patterns` (list of dicts), `user_preferences` (dict), `query_corrections` (list of dicts).
- Settings: 200 examples, 500ms deadline.

---

## Observability Requirements

### OBS-U3-01 — Structured Log Events
- All significant U3 operations emit named log events with consistent `extra` fields (Q7=D, mirroring U2's pattern).
- Logger: `logging.getLogger("agent.kb")` for KnowledgeBase; `logging.getLogger("agent.memory")` for MemoryManager.

### OBS-U3-02 — KnowledgeBase Events

| Event | Level | Key Fields |
|---|---|---|
| `documents_loaded` | INFO | `subdir`, `doc_count`, `from_cache: bool`, `elapsed_ms` |
| `documents_cache_hit` | DEBUG | `subdir`, `doc_count`, `cache_age_s` |
| `document_injected` | INFO | `subdir`, `filename`, `token_estimate` |
| `correction_appended` | INFO | `entry_id`, `failure_type`, `total_count` |
| `corrections_loaded` | INFO | `entry_count`, `skipped_corrupt: int` |
| `correction_corrupt_skipped` | WARNING | `index`, `error` |

### OBS-U3-03 — MemoryManager Events

| Event | Level | Key Fields |
|---|---|---|
| `session_saved` | INFO | `session_id`, `trace_steps`, `elapsed_ms` |
| `session_already_exists` | WARNING | `session_id` |
| `autodream_started` | INFO | `stale_session_count` |
| `autodream_complete` | INFO | `sessions_consolidated`, `sessions_deleted`, `elapsed_ms` |
| `autodream_skipped` | INFO | `reason: "no_stale_sessions"` |
| `autodream_error` | ERROR | `error`, `stage: "staging" \| "rename" \| "cleanup"` |
| `topics_loaded` | DEBUG | `patterns_count`, `corrections_count` |

### OBS-U3-04 — No Sensitive Data in Logs
- Log events MUST NOT include query text, correction content, or session summary text.
- Only counts, IDs, types, and timings are logged.

### OBS-U3-05 — autoDream Background Task Errors Surface
- If `_run_autoDream` raises an unhandled exception, it is caught at the task level, logged at ERROR with full traceback, and the agent continues to run — the background task failure never propagates to the request handler.

---

## Security Requirements

### SEC-U3-01 — No PII in File Names or Log Fields
- Session files use UUID-based session_id only — no usernames, emails, or query fragments in filenames.
- Log event `extra` fields contain only session_id (UUID), counts, and elapsed time — no user-derived content.

### SEC-U3-02 — KB Write Access Control (Operational)
- `inject_document` is called only from trusted internal code (ContextManager or developer tooling) — never from user-supplied input.
- File path is constructed from `subdir` (validated against whitelist) + caller-supplied `filename`; `filename` must not contain `..` or absolute path separators.
- Path traversal guard: `filename` must match `r'^[\w\-. ]+\.md$'` (alphanumeric, dash, dot, space only).
