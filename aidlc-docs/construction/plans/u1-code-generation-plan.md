# U1 Code Generation Plan
# Unit 1 — Agent Core & API

**Status**: In Progress  
**Date**: 2026-04-11

---

## Unit Context

**Requirements**: FR-01 (POST /query), FR-02 (ReAct loop + LLM), FR-03 (context assembly), FR-04 (CorrectionEngine), FR-05 (rate limiting + security headers)  
**Dependencies**: `agent/models.py`, `agent/config.py` (shared), U2 `MultiDBEngine`, U3 `KnowledgeBase`/`MemoryManager`, U5 `SchemaIntrospector`/`MultiPassRetriever`/`JoinKeyUtils`  
**Files Produced**:
- `agent/api/__init__.py` — package marker
- `agent/api/middleware.py` — SecurityHeadersMiddleware + GlobalErrorHandlerMiddleware
- `agent/api/app.py` — FastAPI app, lifespan, routes, rate limiting
- `agent/orchestrator/__init__.py` — package marker
- `agent/orchestrator/react_loop.py` — Orchestrator with ReAct loop
- `agent/context/__init__.py` — package marker
- `agent/context/manager.py` — ContextManager with 3-layer assembly
- `agent/correction/__init__.py` — package marker
- `agent/correction/engine.py` — CorrectionEngine with 5 fix strategies
- `tests/unit/test_api.py` — AgentAPI unit tests
- `tests/unit/test_orchestrator.py` — Orchestrator unit tests + PBT-U1-02
- `tests/unit/test_context_manager.py` — ContextManager unit tests
- `tests/unit/test_correction_engine.py` — CorrectionEngine unit tests + PBT-U1-01
- `aidlc-docs/construction/u1-agent-core-api/code/code-summary.md`

**Design Sources**:
- `aidlc-docs/construction/u1-agent-core-api/functional-design/`
- `aidlc-docs/construction/u1-agent-core-api/nfr-requirements/`
- `aidlc-docs/construction/u1-agent-core-api/nfr-design/`

---

## Extension Compliance

| Extension | Status | Notes |
|---|---|---|
| Security Baseline | Enforced | SEC-U1-01 (no content in logs), SEC-U1-02 (security headers), SEC-U1-03 (error sanitization) |
| Property-Based Testing | Enforced | 2 blocking PBT properties (PBT-U1-01, PBT-U1-02) |

---

## Code Generation Steps

- [x] **Step 1** — Create `agent/api/__init__.py`  
  Package marker; exports `create_app` at package level.

- [x] **Step 2** — Create `agent/api/middleware.py`  
  Implements:
  - `SecurityHeadersMiddleware(BaseHTTPMiddleware)` — adds X-Content-Type-Options, X-Frame-Options, CSP
  - `GlobalErrorHandlerMiddleware(BaseHTTPMiddleware)` — ASGI-level catch; returns sanitized 500 JSON
  - `_log_security_event(event, path)` — structured log helper (no content)

- [x] **Step 3** — Create `agent/api/app.py`  
  Implements:
  - `create_app()` — factory function; registers middleware, lifespan, routes
  - `lifespan(app)` — `@asynccontextmanager`; startup: init KB/memory/context/orchestrator + tasks; shutdown: cancel tasks
  - `handle_query(request)` — POST /query; validates → session → context → run → save → respond
  - `health_check()` — GET /health; probes MCP Toolbox; returns HealthResponse
  - `get_schema_info()` — GET /schema; returns SchemaResponse from cache
  - `_log_request_complete(...)` — 6-field structured log (Pattern 5)
  - Rate limiter: `slowapi.Limiter` on `handle_query`
  - `@app.exception_handler(Exception)` — Layer A error handler (Pattern 4)

- [x] **Step 4** — Create `agent/orchestrator/__init__.py`  
  Package marker; exports `Orchestrator`.

- [x] **Step 5** — Create `agent/orchestrator/react_loop.py`  
  Implements:
  - `Orchestrator.__init__(llm_client, engine, kb, memory, retriever)` — DI pattern (Pattern 6)
  - `run(query, session_id, context, max_iterations, confidence_threshold)` — main ReAct loop (BR-U1-03/04)
  - `think(state, context)` — LLM call → JSON parse → Thought (Q1=B format, Q3=A confidence)
  - `act(thought, context)` — tool dispatch (query_database/search_kb/extract_from_text/resolve_join_keys/FINAL_ANSWER)
  - `observe(observation, state)` — ReactState update + termination check
  - `_call_llm(messages, _attempt)` — ExponentialBackoffRetry (Pattern 1; RateLimitError only)
  - `_build_messages(state, context)` — PromptCacheBuilder (Pattern 2; static cache + dynamic)
  - `_get_static_prompt(context)` — lazy build; cached in `self._static_prompt`
  - `_format_corrections(corrections_ctx)` — markdown bullets (Q7=B)
  - `_format_history(history)` — TraceStep list → message dicts
  - `_handle_correction(failure, plan, context)` — CorrectionEngine integration (Q5=B)
  - `_log_think_step(session_id, iteration, action)` — DEBUG log (no content; SEC-U1-01)
  - `_log_act_step(session_id, iteration, success, elapsed_ms)` — DEBUG log

- [x] **Step 6** — Create `agent/context/__init__.py`  
  Package marker; exports `ContextManager`.

- [x] **Step 7** — Create `agent/context/manager.py`  
  Implements:
  - `ContextManager.__init__(kb, memory, schema_introspector)` — DI
  - `startup_load()` — Layer 1 via SchemaIntrospector; Layer 2 initial load; stores `_layer2_loaded_at`
  - `get_context_bundle(session_id)` — assemble ContextBundle; mtime check for Layer 2 (Q6=A); fresh Layer 3
  - `_check_layer2_staleness()` — compare file mtimes against `_layer2_loaded_at`
  - `_load_layer2()` — KnowledgeBase.load_documents() for all subdirs
  - `_load_layer3(session_id)` — get_corrections() + get_topics() → CorrectionsContext
  - `_format_layer3_for_prompt(corrections_ctx)` — markdown bullets (Q7=B)
  - `_refresh_layer2_loop()` — infinite asyncio loop; sleeps `layer2_refresh_interval_s`; calls `_check_layer2_staleness()`
  - `invalidate_layer2_cache()` — sets `_layer2_loaded_at = 0.0` (force-reload)
  - `_log_context_assembled(session_id, layer2_doc_count, correction_count, elapsed_ms)` — structured log

- [x] **Step 8** — Create `agent/correction/__init__.py`  
  Package marker; exports `CorrectionEngine`.

- [x] **Step 9** — Create `agent/correction/engine.py`  
  Implements:
  - `CorrectionEngine.__init__(llm_client, engine)` — DI
  - `correct(failure, original_query, context, attempt)` — tiered dispatch; raises `CorrectionExhausted` if attempt > max
  - `classify_failure(failure)` — rule-based pattern match → FailureType (BR-U1-08)
  - `fix_syntax_error(query, error)` — 4 rule-based transforms (BR-U1-09/Q9=C)
  - `fix_join_key(query, mismatch)` — JoinKeyUtils-based rewriter
  - `fix_wrong_db_type(plan, failure)` — db_type signal patterns → swap (BR-U1-10/Q10=B)
  - `fix_data_quality(query, failure)` — COALESCE/IFNULL null-guard insertion
  - `llm_correct(query, error, context)` — LLM call with error + schema context
  - `_log_correction_attempt(session_id, attempt, failure_type, strategy, success)` — structured log (no query content)
  - `CorrectionExhausted` exception class

- [x] **Step 10** — Update `tests/unit/strategies.py`  
  Add U1 invariant settings:
  - `"PBT-U1-01": settings(max_examples=300, deadline=timedelta(milliseconds=200))`
  - `"PBT-U1-02": settings(max_examples=200, deadline=timedelta(milliseconds=200))`
  Add `execution_failures()` composite strategy for PBT-U1-01.

- [x] **Step 11** — Create `tests/unit/test_correction_engine.py`  
  Unit tests + PBT-U1-01:
  - `classify_failure` covers all 5 FailureType branches
  - `fix_syntax_error` handles all 4 rule patterns; does not truncate output
  - `fix_wrong_db_type` reroutes correctly for each DB signal set
  - `fix_data_quality` inserts COALESCE/IFNULL without breaking query structure
  - `correct()` raises `CorrectionExhausted` after `max_correction_attempts`
  - `correct()` routes to correct strategy per FailureType
  - **PBT-U1-01**: `classify_failure(failure)` always returns valid FailureType, never raises (300 examples)

- [x] **Step 12** — Create `tests/unit/test_orchestrator.py`  
  Unit tests + PBT-U1-02:
  - `run()` terminates on FINAL_ANSWER action
  - `run()` returns confidence=0.0 + "could not answer" when max_iterations reached (Q2=C)
  - `think()` parses valid LLM JSON response to Thought
  - `think()` handles malformed JSON (graceful fallback)
  - `_call_llm()` retries on RateLimitError up to 3×; propagates after 3 failures
  - `_call_llm()` does NOT retry on non-rate-limit errors
  - `_build_messages()` uses cached static prompt on second call
  - **PBT-U1-02**: `fix_syntax_error(query, error)` output always has len >= input len (200 examples)

- [x] **Step 13** — Create `tests/unit/test_context_manager.py`  
  Unit tests:
  - `startup_load()` calls SchemaIntrospector and loads Layer 2 docs
  - `get_context_bundle()` returns all 3 layers
  - Layer 2 cache hit: same docs returned when no mtime change
  - Layer 2 reload: new docs returned after `invalidate_layer2_cache()`
  - Layer 3 always loads fresh (no caching)

- [x] **Step 14** — Create `tests/unit/test_api.py`  
  Unit tests:
  - `POST /query` with valid request → 200 + QueryResponse
  - `POST /query` with empty question → 422
  - `POST /query` with question > 4096 chars → 422
  - `POST /query` with caller-provided session_id → session_id echoed in response (Q11=B)
  - `POST /query` when Orchestrator raises → 500 with sanitized error (SEC-U1-03)
  - `GET /health` → 200 with mcp_toolbox field
  - `GET /schema` → 200 with databases field
  - Security headers present on all responses (SEC-U1-02)
  - Rate limit: 21st request in 1 minute → 429

- [x] **Step 15** — Create `aidlc-docs/construction/u1-agent-core-api/code/code-summary.md`  
  Summary table of all generated files, key design decisions, PBT properties, security compliance.

---

## Completion Criteria

- All 15 steps marked [x]
- Application code in `agent/api/`, `agent/orchestrator/`, `agent/context/`, `agent/correction/` (never in aidlc-docs/)
- Security rules: SEC-U1-01 (no content in logs), SEC-U1-02 (headers), SEC-U1-03 (error sanitization)
- 2 PBT properties present: PBT-U1-01 (classify_failure, 300 examples), PBT-U1-02 (fix_syntax_error output length, 200 examples)
- All NFR design patterns implemented: ExponentialBackoffRetry, PromptCacheBuilder, ASGISecurityMiddleware, DualLayerErrorHandler, StructuredRequestLogger, DependencyInjectedLLMClient, LifespanManagedTasks
