# Logical Components
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## Component Map

```
agent/api/
  app.py
    FastAPI app instance
    lifespan context manager          (Pattern 7: LifespanManagedTasks)
    RateLimitMiddleware (slowapi)
    SecurityHeadersMiddleware         (Pattern 3: ASGISecurityMiddleware)
    GlobalErrorHandlerMiddleware      (Pattern 4: DualLayerErrorHandler — Layer B)
    @exception_handler(Exception)     (Pattern 4: DualLayerErrorHandler — Layer A)
    handle_query()                    POST /query route
    health_check()                    GET /health route
    get_schema_info()                 GET /schema route
    _log_request_complete()           (Pattern 5: StructuredRequestLogger)

  middleware.py
    SecurityHeadersMiddleware         (BaseHTTPMiddleware)
    GlobalErrorHandlerMiddleware      (BaseHTTPMiddleware)

agent/orchestrator/
  react_loop.py
    Orchestrator                      (Pattern 6: DependencyInjectedLLMClient)
      run()                           main ReAct loop
      think()                         LLM call → Thought
      act()                           tool dispatch → Observation
      observe()                       state update + termination check
      _call_llm()                     (Pattern 1: ExponentialBackoffRetry)
      _build_messages()               (Pattern 2: PromptCacheBuilder)
      _get_static_prompt()            cached static prompt builder
      _format_corrections()           Layer 3 → markdown bullets
      _format_history()               TraceStep list → messages
      _handle_correction()            CorrectionEngine integration
      _log_think_step()               structured DEBUG log (no content)
      _log_act_step()                 structured DEBUG log (no content)

agent/context/
  manager.py
    ContextManager
      startup_load()                  Layer 1 (SchemaIntrospector) + start Layer 2 task
      get_context_bundle()            assembles all 3 layers
      _refresh_layer2_if_stale()      mtime check → reload (Q6=A)
      _refresh_layer2_loop()          background asyncio.Task (Q8=B)
      invalidate_layer2_cache()       force-reload for tests
      _load_layer3()                  KnowledgeBase.get_corrections() + MemoryManager.get_topics()
      _format_layer3_for_prompt()     → markdown bullets (Q7=B)

agent/correction/
  engine.py
    CorrectionEngine
      correct()                       main entry; routes to fix strategy
      classify_failure()              rule-based; returns FailureType
      fix_syntax_error()              rule-based rewriter (Q9=C patterns)
      fix_join_key()                  JoinKeyUtils-based rewriter
      fix_wrong_db_type()             db_type signal pattern rerouter (Q10=B)
      fix_data_quality()              COALESCE/IFNULL null-guard adder
      llm_correct()                   last-resort LLM call (ExponentialBackoffRetry)
      _log_correction_attempt()       structured log (no query content)
```

---

## Component Responsibilities

### `app.py` — AgentAPI

| Component | Type | Responsibility |
|---|---|---|
| FastAPI app | Framework | Routes, middleware registration, lifespan |
| `lifespan` | `@asynccontextmanager` | Startup: SchemaIntrospector, background tasks; Shutdown: task cancellation |
| `RateLimitMiddleware` | slowapi | 20 req/min per IP on POST /query |
| `SecurityHeadersMiddleware` | BaseHTTPMiddleware | 3 security headers on every response |
| `GlobalErrorHandlerMiddleware` | BaseHTTPMiddleware | ASGI-level exception catch → 500 JSON |
| `handle_query()` | route | Validate → session → context → orchestrate → save → respond |
| `_log_request_complete()` | helper | 6-field structured log; no content |

### `react_loop.py` — Orchestrator

| Component | Type | Responsibility |
|---|---|---|
| `Orchestrator.__init__` | DI receiver | Accepts `llm_client`, `engine`, `kb`, `memory` |
| `run()` | async method | ReAct loop driver; terminates on FINAL_ANSWER or max_iterations |
| `think()` | async method | LLM call; parses JSON response to Thought |
| `act()` | async method | Dispatches to tool; returns Observation |
| `observe()` | sync method | Updates ReactState; sets `terminated` flag |
| `_call_llm()` | async method | Retry with exponential backoff (RateLimitError only) |
| `_build_messages()` | sync method | Static cache + dynamic corrections + history |
| `_get_static_prompt()` | sync method | Lazy-built; invalidated on Layer 2 cache miss |

### `manager.py` — ContextManager

| Component | Type | Responsibility |
|---|---|---|
| `startup_load()` | async method | Layer 1 via SchemaIntrospector; stores in `self._schema_ctx` |
| `get_context_bundle()` | async method | Assembles ContextBundle; checks Layer 2 mtime |
| `_refresh_layer2_loop()` | async coroutine | Infinite loop; sleeps `layer2_refresh_interval_s`; checks mtime |
| `_load_layer3()` | sync method | KnowledgeBase.get_corrections() + MemoryManager.get_topics() |

### `engine.py` — CorrectionEngine

| Component | Type | Responsibility |
|---|---|---|
| `correct()` | async method | Routes to fix strategy by FailureType; tracks attempt count |
| `classify_failure()` | sync function | Pattern match on `error_message`; returns `FailureType` |
| `fix_syntax_error()` | sync function | 4 rule-based transformations (Q9=C) |
| `fix_wrong_db_type()` | sync function | DB signal patterns → swap `db_type` (Q10=B) |
| `fix_data_quality()` | sync function | NULL guard insertion |
| `llm_correct()` | async method | LLM call with error + schema context |

---

## Inter-Component Dependencies

```
AgentAPI
  → ContextManager.get_context_bundle()        (per request)
  → Orchestrator.run()                          (per request)
  → MemoryManager.save_session()               (after run, best-effort)

Orchestrator
  → MultiDBEngine.execute_plan()               (act: query_database)
  → KnowledgeBase.load_documents()             (act: search_kb)
  → CorrectionEngine.correct()                 (on DB failure)
  → KnowledgeBase.append_correction()          (after each correction attempt)
  → MultiPassRetriever.retrieve()              (act: search_kb — text match)
  → JoinKeyResolver.pre_execute_resolve()      (act: resolve_join_keys)

ContextManager
  → SchemaIntrospector.introspect_all()        (startup: Layer 1)
  → KnowledgeBase.load_documents()             (Layer 2 domain docs)
  → KnowledgeBase.get_corrections()            (Layer 3 corrections)
  → MemoryManager.get_topics()                 (Layer 3 session memory)

CorrectionEngine
  → JoinKeyUtils                               (fix_join_key)
  → MultiDBEngine.execute_plan()               (re-execute corrected plan)
  → openai.AsyncOpenAI                         (llm_correct — DI injected)
```

---

## Sequence: Successful Query (Happy Path)

```
Client          AgentAPI         ContextManager    Orchestrator      MultiDBEngine
  |                |                  |                 |                 |
  |--POST /query-->|                  |                 |                 |
  |                |--get_bundle()--->|                 |                 |
  |                |<--ContextBundle--|                 |                 |
  |                |--run(q, ctx)------------------->   |                 |
  |                |                                    |--think()        |
  |                |                                    |  (LLM call)     |
  |                |                                    |--act()          |
  |                |                                    |--execute_plan()->|
  |                |                                    |<--ExecutionResult|
  |                |                                    |--think()        |
  |                |                                    |  FINAL_ANSWER   |
  |                |<--OrchestratorResult---------------|                 |
  |                |--save_session() (best-effort)      |                 |
  |<--QueryResponse|                                    |                 |
```
