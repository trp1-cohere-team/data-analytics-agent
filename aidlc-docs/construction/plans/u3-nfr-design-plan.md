# U3 NFR Design Plan
# Unit 3 — Knowledge Base & Memory System

**Status**: Complete  
**Date**: 2026-04-11

---

## NFR Design Steps

- [x] Step 1 — Analyze NFR requirements
- [x] Step 2 — Generate questions and collect answers
- [x] Step 3 — Generate nfr-design-patterns.md
- [x] Step 4 — Generate logical-components.md
- [x] Step 5 — Update audit.md and aidlc-state.md

---

## Questions for User

**Instructions**: Fill in an [Answer]: tag for each question below, then reply "am done".

---

### Performance Pattern — Async I/O

**Q1** — File operations (`Path.read_text`, `Path.write_text`, `Path.replace`) are synchronous and will block the asyncio event loop. U3 is called from U1's async request handlers. How should blocking disk I/O be handled?

A) Wrap all disk I/O in `asyncio.to_thread()` — non-blocking for the event loop; adds minor thread overhead  
B) Leave as synchronous — local SSD I/O is fast enough (< 1ms); blocking the loop for KB loads is acceptable  
C) Wrap only autoDream I/O in `asyncio.to_thread()` — request-path calls (load_documents, append_correction) stay synchronous since they're short  
D) Use `aiofiles` library for async file I/O throughout — true async without thread pool overhead

[Answer]:A

---

### Resilience Pattern — Stale Staging Directory

**Q2** — At autoDream startup, if `topics/.staging/` already exists from a previously failed run, what should happen?

A) Wipe it — remove all files in `.staging/` before starting a new consolidation (fresh start)  
B) Treat it as a completed-but-not-renamed run — attempt to rename staging files to final locations and skip re-consolidation  
C) Abort this consolidation run — log a WARNING and return; next startup will retry  
D) Use a unique timestamped staging dir (`topics/.staging-{timestamp}/`) so old staging dirs never conflict

[Answer]:A

---

### Lock Scope — asyncio.Lock for corrections

**Q3** — The `asyncio.Lock` for `append_correction` (CONC-U3-01): what scope should it have?

A) Module-level global — one lock for all KnowledgeBase instances in the process (safe for production; harder to isolate in tests)  
B) Instance-level — each KnowledgeBase instance has its own lock (better test isolation; safe since single KnowledgeBase instance in production)  
C) Class variable — shared across all instances of the same class (middle ground)

[Answer]:B

---
