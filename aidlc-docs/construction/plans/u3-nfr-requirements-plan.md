# U3 NFR Requirements Plan
# Unit 3 — Knowledge Base & Memory System

**Status**: Complete  
**Date**: 2026-04-11

---

## NFR Assessment Steps

- [x] Step 1 — Analyze functional design (business-logic-model.md, business-rules.md)
- [x] Step 2 — Generate NFR questions and collect answers
- [x] Step 3 — Generate nfr-requirements.md
- [x] Step 4 — Generate tech-stack-decisions.md
- [x] Step 5 — Update audit.md and aidlc-state.md

---

## Questions for User

**Instructions**: Fill in an [Answer]: tag for each question below, then reply "am done".

---

### Concurrency & File Safety

**Q1** — Multiple agent sessions can run concurrently and all call `append_correction`. The atomic `.tmp`→rename pattern prevents mid-write corruption, but two concurrent calls can still overwrite each other's updates (last-write-wins race). How should this be handled?

A) Accept last-write-wins — corrections log is a best-effort audit trail; rare races are tolerable  
B) Use `filelock` library (`FileLock`) — acquire an exclusive lock around the read-modify-write cycle  
C) Use OS-level `fcntl.flock` / `msvcrt.locking` for POSIX/Windows — no extra dependency  
D) Serialize all writes through a single `asyncio.Lock` in-process — no cross-process safety needed (single-process deployment)

[Answer]:D

---

**Q2** — Same concurrency question for `save_session` (MemoryManager). Multiple calls with different `session_id` values write to separate files — no conflict. But if two calls somehow use the same `session_id` (race before the existence check), what happens?

A) Acceptable — the write-once check (log warning + return) is sufficient; duplicate session_id is a caller bug  
B) Use an in-process `asyncio.Lock` keyed by session_id — prevents the race  
C) Acquire an exclusive file lock on the target path before writing — prevents both in-process and cross-process races

[Answer]:B

---

### autoDream Reliability

**Q3** — If `_run_autoDream()` fails mid-consolidation (e.g., one topic file write succeeds but the second fails), what should happen?

A) Log the error and abort — partial consolidation is acceptable; next startup will retry and may re-process the same sessions (idempotent by session_id dedup)  
B) Full rollback — write all three topic files in a single transaction using a staging directory; only replace originals once all three are written  
C) Retry with exponential backoff (up to 3 attempts) before giving up  
D) Raise an exception that propagates to the startup caller — agent should not start with a broken memory state

[Answer]:B

---

**Q4** — After autoDream consolidates sessions older than 7 days, should those session files be deleted from `agent/memory/sessions/`?

A) Delete — sessions older than `memory_max_age_days` are removed after successful consolidation (keeps disk usage bounded)  
B) Keep forever — session files are never deleted; only the topics are updated  
C) Archive — move to `agent/memory/archive/{session_id}.json` rather than delete  
D) Configurable — controlled by a `memory_delete_after_consolidation: bool` setting (default True)

[Answer]:D

---

### Property-Based Testing (PBT Extension — blocking)

**Q5** — Which PBT invariant properties should be enforced for KnowledgeBase? Select all that apply (choose a combined letter):

A) Round-trip: `CorrectionEntry` serialized to JSON and deserialized produces an identical object  
B) Append-only: `append_correction` called N times always results in `len(get_corrections()) == N` (starting from empty)  
C) Injection safety: `inject_document` with content > 4k tokens always raises `ValueError`; with ≤4k always succeeds  
D) All three (A + B + C)

[Answer]:D

---

**Q6** — Which PBT invariant properties should be enforced for MemoryManager?

A) Write-once: calling `save_session` twice with the same session_id never increases the number of session files  
B) Topic merge idempotency: consolidating the same session twice produces the same topic state as consolidating it once  
C) Round-trip: `SessionMemory` serialized and loaded produces identical object  
D) All three (A + B + C)

[Answer]:D

---

### Observability

**Q7** — What level of logging should U3 emit?

A) Minimal — only errors (failed writes, parse failures)  
B) Standard — INFO for each document load, correction append, session save; WARNING for cache invalidations and autoDream skip  
C) Verbose — DEBUG for every cache hit/miss, every file open/close, every topic merge step  
D) Structured (like U2's ObservabilityEmitter) — named log events with consistent extra fields (subdir, session_id, entry_count, elapsed_ms)

[Answer]:D

---
