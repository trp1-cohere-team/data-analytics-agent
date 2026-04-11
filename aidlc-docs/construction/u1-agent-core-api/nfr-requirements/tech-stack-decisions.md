# Tech Stack Decisions
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## Decision Table

| Area | Decision | Rationale |
|---|---|---|
| Web framework | FastAPI | Async-native, Pydantic integration, automatic OpenAPI docs |
| ASGI server | Uvicorn (direct, no Gunicorn) | Q9=A: single-process dev/production; concurrency via asyncio |
| Rate limiting | slowapi (`Limiter`) | FastAPI-native integration, decorator-based per-route limits |
| LLM client | `openai.AsyncOpenAI` (OpenRouter base_url) | Async, reuses existing SDK; OpenRouter is OpenAI-compatible |
| LLM client lifecycle | Injected via `__init__` (DI) | Q10=C: enables unit testing with mock client; no module-level singleton |
| HTTP middleware | Custom ASGI middleware class | Security headers + global error handler in one place |
| Logging | Python stdlib `logging` + structured `extra={}` dict | Consistent with U2/U3 pattern; no external logging library |
| Config | `pydantic-settings` `Settings` (shared `agent/config.py`) | Already established in shared infrastructure |

---

## Package Dependencies (U1-specific additions)

| Package | Version constraint | Purpose |
|---|---|---|
| `fastapi` | `>=0.110` | Web framework |
| `uvicorn[standard]` | `>=0.29` | ASGI server |
| `slowapi` | `>=0.1.9` | Rate limiting middleware for FastAPI |
| `openai` | `>=1.14` | LLM client (OpenAI-compatible; used with OpenRouter base_url) |

Dependencies already present from U2/U3/U5:
- `pydantic`, `pydantic-settings`, `aiohttp`, `asyncio` (stdlib)

---

## PBT Extension

| ID | Scope | Description | Examples |
|---|---|---|---|
| PBT-U1-01 | `classify_failure` | Any `ExecutionFailure.error_message` always returns a valid `FailureType` (never raises) | 300 |
| PBT-U1-02 | `fix_syntax_error` | Output is always a string of the same or greater length than input (no truncation) | 200 |

---

## Security Extension Compliance

| Rule | Status | Implementation |
|---|---|---|
| SEC-U1-01: No content in logs | Enforced | `_log_request_complete()` logs metadata only; `question` and `answer` excluded |
| SEC-U1-02: Security headers | Enforced | `SecurityHeadersMiddleware` adds 3 headers to every response |
| SEC-U1-03: Error sanitization | Enforced | Global error handler returns exception type name only |

---

## Architecture Notes

### LLM Client Injection Pattern
```python
class Orchestrator:
    def __init__(self, llm_client: openai.AsyncOpenAI, ...) -> None:
        self._llm = llm_client
```
AgentAPI constructs `Orchestrator(llm_client=AsyncOpenAI(base_url=..., api_key=...))` at startup. Tests inject a mock.

### Middleware Stack (request order)
```
1. RateLimitMiddleware (slowapi)   — rejects >20/min before processing
2. SecurityHeadersMiddleware       — adds response headers
3. GlobalErrorHandlerMiddleware    — catches all unhandled exceptions
4. FastAPI route handlers
```

### ContextManager Lifecycle
```
FastAPI lifespan context manager:
  @asynccontextmanager
  async def lifespan(app):
      await context_manager.startup_load()   # Layer 1 + Layer 2 + background task
      yield
      # shutdown: cancel background tasks
```
