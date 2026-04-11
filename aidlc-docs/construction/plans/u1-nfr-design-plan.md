# U1 NFR Design Plan
# Unit 1 — Agent Core & API

**Status**: In Progress  
**Date**: 2026-04-11

---

## NFR Design Questions

### Resilience Patterns

**Q1** — Which retry pattern governs LLM `RateLimitError` retries?

A) Simple fixed-delay retry (same wait each time)  
B) Exponential backoff without jitter  
C) Exponential backoff with jitter (randomized wait to avoid thundering herd)  
D) Circuit breaker — open after N failures, half-open probe after timeout  

[Answer]: B

---

**Q2** — Should a circuit breaker be applied to the LLM client calls?

A) Yes — open circuit after 3 consecutive non-rate-limit failures; half-open probe every 60s  
B) No — simple retry with backoff is sufficient for a small-team API  
C) Yes — but only for timeout errors, not connection errors  
D) Defer to runtime monitoring; not in code  

[Answer]: B

---

### Performance Patterns

**Q3** — How should the Orchestrator system prompt be managed for performance?

A) Build from scratch on every `run()` call (no caching)  
B) Cache the static parts (schema + domain docs) and rebuild only the dynamic parts (corrections, history) per call  
C) Cache the full rendered prompt per session_id  
D) Pre-render and store as a file at startup  

[Answer]: B

---

**Q4** — Should `ContextManager.get_context_bundle()` be optimized with any async concurrency?

A) Yes — load Layer 1 and Layer 3 concurrently via `asyncio.gather()`  
B) No — sequential loading is fine for the load profile (5–20 concurrent users)  
C) Yes — all three layers loaded concurrently  
D) Only Layer 2 and Layer 3 in parallel  

[Answer]: B

---

### Security Patterns

**Q5** — Which pattern implements the security headers middleware?

A) Per-route decorator (`@app.middleware` on each endpoint)  
B) Single ASGI `BaseHTTPMiddleware` subclass added to the app at startup  
C) FastAPI dependency injection (`Depends(security_headers)`)  
D) Nginx/reverse proxy layer only — not in application code  

[Answer]: B

---

**Q6** — How should the global error handler be implemented?

A) `@app.exception_handler(Exception)` FastAPI hook  
B) Custom ASGI middleware that wraps the full request/response cycle in try/except  
C) Both A (for FastAPI-known exceptions) and B (for ASGI-level exceptions)  
D) Separate error handler class injected into each route  

[Answer]: C

---

### Logical Components

**Q7** — How is the `Orchestrator` LLM client wired at startup?

A) Module-level singleton instantiated at import time  
B) Created in FastAPI `lifespan` context manager; injected into `Orchestrator.__init__`  
C) Created per-request in `handle_query()`  
D) Created by the Orchestrator itself using `settings`  

[Answer]: B

---

**Q8** — Where does the `ContextManager` background refresh task run?

A) Separate process (subprocess or worker)  
B) `asyncio.create_task()` launched in FastAPI `lifespan` context manager  
C) `threading.Thread` running alongside the event loop  
D) External scheduler (cron/celery) triggering a refresh endpoint  

[Answer]: B

---

## Plan Steps

- [x] **Step 1** — Analyze NFR requirements (done above)
- [x] **Step 2** — Generate `nfr-design-patterns.md`
- [x] **Step 3** — Generate `logical-components.md`
- [x] **Step 4** — Update aidlc-state.md and audit.md; present completion message
