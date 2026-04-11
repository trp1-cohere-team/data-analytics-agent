# U1 Code Summary — Agent Core & API

**Unit**: U1 — Agent Core & API  
**Status**: Complete  
**Date**: 2026-04-11

---

## Generated Files

| File | Description | Lines |
|---|---|---|
| `agent/api/__init__.py` | Package marker; exports `create_app` | 3 |
| `agent/api/middleware.py` | SecurityHeadersMiddleware + GlobalErrorHandlerMiddleware | ~65 |
| `agent/api/app.py` | FastAPI factory, lifespan, 3 routes, rate limiter, error handler | ~185 |
| `agent/orchestrator/__init__.py` | Package marker; exports `Orchestrator` | 3 |
| `agent/orchestrator/react_loop.py` | Orchestrator — full ReAct loop with 7 NFR patterns | ~285 |
| `agent/context/__init__.py` | Package marker; exports `ContextManager` | 3 |
| `agent/context/manager.py` | ContextManager — 3-layer assembly + background refresh | ~175 |
| `agent/correction/__init__.py` | Package marker; exports `CorrectionEngine`, `CorrectionExhausted` | 4 |
| `agent/correction/engine.py` | CorrectionEngine — 5 fix strategies + classify_failure | ~230 |
| `tests/unit/strategies.py` | Added PBT-U1-01/02 settings + `execution_failures()` strategy | +20 |
| `tests/unit/test_correction_engine.py` | Unit tests + PBT-U1-01 (classify_failure, 300 examples) | ~195 |
| `tests/unit/test_orchestrator.py` | Unit tests + PBT-U1-02 (fix_syntax_error length, 200 examples) | ~215 |
| `tests/unit/test_context_manager.py` | ContextManager unit tests | ~135 |
| `tests/unit/test_api.py` | API unit tests (validation, session, headers, sanitization) | ~195 |

---

## Internal Components

### `agent/api/middleware.py`

| Component | Pattern | Purpose |
|---|---|---|
| `SecurityHeadersMiddleware` | ASGISecurityMiddleware (Pattern 3) | Adds X-Content-Type-Options, X-Frame-Options, CSP to every response |
| `GlobalErrorHandlerMiddleware` | DualLayerErrorHandler Layer B (Pattern 4) | Catches ASGI-level exceptions; returns sanitized 500 JSON |

### `agent/api/app.py`

| Component | Pattern | Purpose |
|---|---|---|
| `create_app()` | Factory | Registers middleware, lifespan, routes |
| `lifespan()` | LifespanManagedTasks (Pattern 7) | Startup: init all components + background tasks; Shutdown: cancel tasks |
| `handle_query()` | Route | Validate → session → context → orchestrate → save → respond (BR-U1-01/02/14) |
| `health_check()` | Route | Probes MCP Toolbox; returns HealthResponse |
| `get_schema_info()` | Route | Returns Layer 1 schema from cache |
| `_log_request_complete()` | StructuredRequestLogger (Pattern 5) | 6 metadata fields; no content (SEC-U1-01) |
| `@exception_handler(Exception)` | DualLayerErrorHandler Layer A (Pattern 4) | FastAPI-level catch; sanitized 500 |

### `agent/orchestrator/react_loop.py`

| Component | Pattern | Purpose |
|---|---|---|
| `Orchestrator.__init__` | DependencyInjectedLLMClient (Pattern 6) | Receives llm_client, engine, kb, memory, retriever, correction_engine |
| `run()` | ReAct loop | Iterates think→act→observe; terminates on FINAL_ANSWER or max_iterations (BR-U1-03/04) |
| `think()` | — | LLM call → JSON parse → Thought (Q1=B, Q3=A); graceful fallback on parse error |
| `act()` | — | Dispatches to 5 tools; handles query_database failure via CorrectionEngine (Q5=B) |
| `observe()` | — | ReactState update |
| `_call_llm()` | ExponentialBackoffRetry (Pattern 1) | Retries RateLimitError only; 3× at 1s/2s/4s |
| `_build_messages()` | PromptCacheBuilder (Pattern 2) | Static prompt cached by Layer 2 hash; dynamic parts rebuilt per call |
| `_handle_correction()` | — | CorrectionEngine integration; appends correction to KB (Q5=B) |

### `agent/context/manager.py`

| Component | Pattern | Purpose |
|---|---|---|
| `startup_load()` | — | Layer 1 via SchemaIntrospector; Layer 2 initial load |
| `get_context_bundle()` | — | Assembles ContextBundle; mtime check (Q6=A); fresh Layer 3 |
| `_check_and_refresh_layer2()` | — | File mtime scan → all-or-nothing reload (Q6=A) |
| `_load_layer3()` | — | get_corrections() + get_topics() → CorrectionsContext; never cached |
| `_refresh_layer2_loop()` | LifespanManagedTasks (Pattern 7) | Background asyncio.Task; sleeps refresh_interval_s |
| `invalidate_layer2_cache()` | — | Force-reload for tests |

### `agent/correction/engine.py`

| Component | Pattern | Purpose |
|---|---|---|
| `correct()` | Tiered dispatch (BR-U1-08) | Routes to cheapest fix strategy by FailureType |
| `classify_failure()` | Rule-based classifier | Returns FailureType from error signal patterns (BR-U1-08) |
| `fix_syntax_error()` | Rule-based (BR-U1-09/Q9=C) | 4 transforms: missing quotes, GROUP BY, ROWNUM/TOP, ISNULL/NVL |
| `fix_wrong_db_type()` | Signal patterns (BR-U1-10/Q10=B) | DB-specific error signals → swap db_type in QueryPlan |
| `fix_data_quality()` | — | COALESCE null-guard insertion |
| `llm_correct()` | Last resort | LLM call with error + schema context |
| `CorrectionExhausted` | Exception | Raised after max_correction_attempts exceeded (BR-U1-07) |

---

## Design Decisions Implemented

| Decision | Code Location | Description |
|---|---|---|
| Q1=B: System prompt JSON format | `react_loop.py:_build_static_prompt()` | LLM instructed to return `{"reasoning", "action", "action_input", "confidence"}` |
| Q2=C: Max iterations fallback | `react_loop.py:run()` | Returns "could not answer" + confidence=0.0 |
| Q3=A: LLM-reported confidence | `react_loop.py:think()` | Parsed from LLM JSON response |
| Q4=B: Full QueryPlan from LLM | `react_loop.py:_act_query_database()` | `QueryPlan(**inp)` |
| Q5=B: Correction loops to think() | `react_loop.py:_handle_correction()` | Returns correction; observation recorded; next think() sees error |
| Q6=A: mtime-based Layer 2 | `manager.py:_find_changed_file()` | `file.stat().st_mtime > _layer2_loaded_at` |
| Q7=B: Markdown bullets Layer 3 | `react_loop.py:_format_corrections()` | `- [FAILURE_TYPE] \`query...\` → fix_strategy` |
| Q8=A: save_session in AgentAPI | `app.py:handle_query()` | Called after `run()`, before response; best-effort |
| Q9=C: 4 syntax fix patterns | `engine.py:fix_syntax_error()` | ROWNUM, ISNULL, NVL, GROUP BY without aggregate |
| Q10=B: DB signal patterns | `engine.py:fix_wrong_db_type()` | `_DB_ERROR_SIGNALS` dict; swap db_type on match |
| Q11=B: Accept caller session_id | `app.py:handle_query()` | `session_id = body.session_id or str(uuid.uuid4())` |
| Q12=B: 3 security headers | `middleware.py:SecurityHeadersMiddleware` | X-Content-Type-Options, X-Frame-Options, CSP |

---

## PBT Properties

| ID | File | Description | Examples |
|---|---|---|---|
| PBT-U1-01 | `test_correction_engine.py` | `classify_failure()` always returns valid FailureType, never raises | 300 |
| PBT-U1-02 | `test_orchestrator.py` | `fix_syntax_error()` output len always >= input len (no truncation) | 200 |

---

## Security Compliance

| Rule | Status | Implementation |
|---|---|---|
| SEC-U1-01: No content in logs | Compliant | `_log_request_complete()`, `_log_think_step()`, `_log_act_step()` use metadata only |
| SEC-U1-02: Security headers | Compliant | `SecurityHeadersMiddleware` adds 3 headers to every response |
| SEC-U1-03: Error sanitization | Compliant | Both error handler layers return `type(exc).__name__` only |

---

## Dependencies

| Dependency | Imported from |
|---|---|
| `MultiDBEngine.execute_plan()` | U2 `agent/execution/engine.py` |
| `KnowledgeBase` | U3 `agent/kb/knowledge_base.py` |
| `MemoryManager` | U3 `agent/memory/manager.py` |
| `SchemaIntrospector` | U5 `utils/schema_introspector.py` |
| `MultiPassRetriever` | U5 `utils/multi_pass_retriever.py` |
| `JoinKeyUtils` | U5 `utils/join_key_utils.py` |
| `probe_mcp_toolbox` | U2 `agent/execution/mcp_client.py` |
