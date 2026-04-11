# NFR Design Patterns
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API  
**Answers applied**: Q1=B, Q2=B, Q3=B, Q4=B, Q5=B, Q6=C, Q7=B, Q8=B

---

## Pattern 1: ExponentialBackoffRetry (Resilience — Q1=B)

**Applied to**: `Orchestrator._call_llm()` on `RateLimitError`

```
Trigger: openai.RateLimitError (HTTP 429)
Max attempts: 3
Wait schedule: 2^attempt seconds (attempt 0=1s, 1=2s, 2=4s)
No jitter: Q1=B — simple exponential, small team, low collision probability
On exhaustion: propagate RateLimitError → caller treats as LLM unavailable
All other exceptions: no retry, propagate immediately
```

**Code structure**:
```python
async def _call_llm(self, messages, tools, _attempt=0):
    try:
        return await self._llm.chat.completions.create(...)
    except openai.RateLimitError:
        if _attempt >= 2:
            raise
        await asyncio.sleep(2 ** _attempt)
        return await self._call_llm(messages, tools, _attempt + 1)
```

No circuit breaker (Q2=B): simple retry is sufficient for 5–20 concurrent users. Circuit breaker complexity is not justified at this scale.

---

## Pattern 2: PromptCacheBuilder (Performance — Q3=B)

**Applied to**: `Orchestrator.think()` — system prompt construction

Static parts (built once at `Orchestrator.__init__` or first call, cached in `self._static_prompt`):
- Role definition text
- Available actions description
- Schema context (Layer 1 — permanent)
- Domain KB documents (Layer 2 — refreshed when ContextManager invalidates)

Dynamic parts (rebuilt per `think()` call):
- Layer 3 corrections context (markdown bullets — per-session)
- Conversation history (accumulated `TraceStep` list)

```python
def _build_messages(self, state: ReactState, context: ContextBundle) -> list[dict]:
    static = self._get_static_prompt(context)   # cached
    dynamic = self._format_corrections(context.corrections_ctx)
    history = self._format_history(state.history)
    return [
        {"role": "system", "content": static + "\n\n" + dynamic},
        *history,
        {"role": "user", "content": state.query},
    ]
```

No per-call schema serialization. Layer 2 invalidation triggers `self._static_prompt = None` (lazy rebuild on next call).

Sequential context loading (Q4=B): `get_context_bundle()` loads layers sequentially. Async concurrency not needed at 5–20 users; sequential code is simpler and easier to debug.

---

## Pattern 3: ASGISecurityMiddleware (Security — Q5=B)

**Applied to**: All HTTP responses

Single `BaseHTTPMiddleware` subclass added at app initialization:

```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
```

Applied before route handlers in the middleware stack.

---

## Pattern 4: DualLayerErrorHandler (Security — Q6=C)

**Applied to**: FastAPI application — catches all exception types

Two-layer approach:
- **Layer A**: `@app.exception_handler(Exception)` — catches FastAPI-routed exceptions (HTTPException, RequestValidationError, unhandled route exceptions)
- **Layer B**: `GlobalErrorHandlerMiddleware(BaseHTTPMiddleware)` — catches ASGI-level exceptions that bypass FastAPI routing

```python
# Layer A — FastAPI hook
@app.exception_handler(Exception)
async def _global_exception_handler(request, exc):
    _logger.error("unhandled_exception", extra={"type": type(exc).__name__})
    return JSONResponse(
        status_code=500,
        content={"error": "query_failed", "message": type(exc).__name__},
    )

# Layer B — ASGI middleware (catches pre-routing errors)
class GlobalErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            _logger.error("asgi_exception", extra={"type": type(exc).__name__})
            return JSONResponse(
                status_code=500,
                content={"error": "query_failed", "message": type(exc).__name__},
            )
```

---

## Pattern 5: StructuredRequestLogger (Observability)

**Applied to**: `AgentAPI.handle_query()` — logs at completion of each request

```python
def _log_request_complete(session_id, iterations_used, confidence, elapsed_ms, correction_count, action_sequence):
    _logger.info("request_complete", extra={
        "session_id": session_id,
        "iterations_used": iterations_used,
        "confidence": confidence,
        "elapsed_ms": round(elapsed_ms, 1),
        "correction_count": correction_count,
        "action_sequence": action_sequence,
    })
```

No `question` text, no `answer` content, no DB row data (SEC-U1-01).

---

## Pattern 6: DependencyInjectedLLMClient (Testability — Q7=B)

**Applied to**: `Orchestrator.__init__` — LLM client injected, not created internally

```python
class Orchestrator:
    def __init__(
        self,
        llm_client: openai.AsyncOpenAI,
        engine: MultiDBEngine,
        kb: KnowledgeBase,
        memory: MemoryManager,
    ) -> None:
        self._llm = llm_client
        self._engine = engine
        self._kb = kb
        self._memory = memory
```

At startup (FastAPI lifespan): `Orchestrator(llm_client=AsyncOpenAI(...), ...)`.  
In tests: `Orchestrator(llm_client=MockLLMClient(), ...)`.

---

## Pattern 7: LifespanManagedTasks (Reliability — Q8=B)

**Applied to**: FastAPI `lifespan` context manager — manages startup/shutdown of long-lived resources

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    llm_client = openai.AsyncOpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)
    await context_manager.startup_load()
    refresh_task = asyncio.create_task(context_manager._refresh_layer2_loop())
    autodream_task = asyncio.ensure_future(memory_manager._run_autodream())
    yield
    # Shutdown
    refresh_task.cancel()
    autodream_task.cancel()
    await asyncio.gather(refresh_task, autodream_task, return_exceptions=True)
```

All background tasks are `asyncio.Task` objects — no threads, no subprocesses. Cancelled cleanly on shutdown.
