# Unit of Work
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Construction Order**: U5 → U2 → U1 → U3 → U4 (dependency-first)  
**Deployment Model**: Single Python package (monolith with layered modules)

---

## Cross-Unit Shared Infrastructure

These modules are created before any unit and imported by all:

### `agent/models.py` — Shared Data Models
All shared Pydantic/dataclass types used across unit boundaries:

```
QueryRequest, QueryResponse, HealthResponse, SchemaResponse
QueryPlan, SubQuery, MergeSpec
ExecutionResult, SubQueryResult, ExecutionFailure
ContextBundle, SchemaContext, DomainContext, CorrectionsContext
DBSchema, KBDocument, CorrectionEntry
ReactState, Thought, Observation, TraceStep, OrchestratorResult
SessionMemory, SuccessfulPattern
CorrectionResult, FailureType, JoinKeyMismatch, JoinKeyFormat
BenchmarkResult, DABQuery, JudgeVerdict, RegressionResult
```

### `agent/config.py` — Central Configuration
`pydantic-settings` `Settings` class — reads from `.env` + environment:

```
OPENROUTER_API_KEY: str
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL: str = "openai/gpt-4o"
MCP_TOOLBOX_URL: str = "http://localhost:5000"
AGENT_PORT: int = 8000
RATE_LIMIT: str = "20/minute"
MAX_REACT_ITERATIONS: int = 10
CONFIDENCE_THRESHOLD: float = 0.85
MAX_CORRECTION_ATTEMPTS: int = 3
LAYER2_REFRESH_INTERVAL_S: int = 60
CORRECTIONS_LIMIT: int = 50
MEMORY_MAX_AGE_DAYS: int = 7
KB_DIR: Path = Path("kb")
MEMORY_DIR: Path = Path("agent/memory")
RESULTS_DIR: Path = Path("results")
```

### `tests/integration/` — Integration Test Suite
Cross-unit integration tests (Orchestrator↔MultiDBEngine↔MCP Toolbox, full query end-to-end). Run separately from unit tests with `pytest tests/integration/`.

---

## Unit 1: Agent Core & API

**ID**: U1  
**Build Position**: 3rd (after U5 and U2)  
**Layer**: API + Orchestration

### Components
| Component | File | Responsibility |
|---|---|---|
| AgentAPI | `agent/api/app.py` | FastAPI server, request validation, session management, error handling |
| Orchestrator | `agent/orchestrator/react_loop.py` | ReAct loop, LLM calls, tool dispatch, trace recording |
| ContextManager | `agent/context/manager.py` | Three-layer context assembly, caching, background refresh |
| CorrectionEngine | `agent/correction/engine.py` | Failure classification, tiered fix strategies, corrections log |

### Directory Structure
```
agent/
  api/
    app.py              (AgentAPI — FastAPI app, routes, middleware)
    middleware.py       (security headers, global error handler)
  orchestrator/
    react_loop.py       (Orchestrator — ReAct loop, think/act/observe)
  context/
    manager.py          (ContextManager — cache + layer assembly)
  correction/
    engine.py           (CorrectionEngine — classifier + fix strategies)
  models.py             (shared — created before U1)
  config.py             (shared — created before U1)
tests/
  unit/
    test_api.py
    test_orchestrator.py
    test_context_manager.py
    test_correction_engine.py
```

### External Dependencies
- **Imports from U2**: `MultiDBEngine.execute_plan()`
- **Imports from U5**: `SchemaIntrospector`, `MultiPassRetriever`, `JoinKeyUtils`
- **Imports from U3**: `KnowledgeBase`, `MemoryManager`
- **External**: `openai.AsyncOpenAI` (OpenRouter), `fastapi`, `pydantic`, `slowapi`

### Key NFRs for This Unit
- Rate limiting on `/query`: 20 req/min (slowapi)
- Security headers middleware: X-Content-Type-Options, X-Frame-Options, CSP
- Global error handler: never expose stack traces
- API key from environment only (`config.py`)
- All LLM calls: max 3 retries with exponential backoff on rate limit

---

## Unit 2: Multi-DB Execution Engine

**ID**: U2  
**Build Position**: 2nd (after U5)  
**Layer**: Execution

### Components
| Component | File | Responsibility |
|---|---|---|
| MultiDBEngine | `agent/execution/engine.py` | Top-level executor: route, fan-out, merge |
| QueryRouter | (internal to engine.py) | Reads `db_type` from QueryPlan, dispatches to connector |
| PostgreSQLConnector | (internal) | Calls MCP Toolbox `postgres_query` |
| SQLiteConnector | (internal) | Calls MCP Toolbox `sqlite_query` |
| MongoDBConnector | (internal) | Calls MCP Toolbox `mongodb_aggregate` |
| DuckDBConnector | (internal) | Calls MCP Toolbox `duckdb_query` |
| JoinKeyResolver | (internal, delegates to U5) | Detects and transforms cross-DB join key mismatches |
| ResultMerger | (internal) | Merges sub-query results per MergeSpec |

### Directory Structure
```
agent/
  execution/
    engine.py           (MultiDBEngine — all sub-components internal)
    mcp_client.py       (aiohttp HTTP client for MCP Toolbox calls)
tests/
  unit/
    test_execution_engine.py
    test_mcp_client.py
```

### External Dependencies
- **Imports from U5**: `JoinKeyUtils` (detect_format, build_transform_expression, transform_key)
- **External**: `aiohttp` (MCP Toolbox HTTP), `agent/config.py` (MCP_TOOLBOX_URL, timeout)

### Key NFRs for This Unit
- All DB calls: async (aiohttp), 30s timeout per sub-query
- Errors: wrapped as `ExecutionFailure` — never raised raw to caller
- MCP Toolbox connection: no auth (localhost only); URL from config
- Sub-queries fan out concurrently via `asyncio.gather`

---

## Unit 3: Knowledge Base & Memory System

**ID**: U3  
**Build Position**: 4th (independent; built after U1)  
**Layer**: Knowledge

### Components
| Component | File | Responsibility |
|---|---|---|
| KnowledgeBase | `agent/kb/knowledge_base.py` | File-system read/write for KB documents and corrections log |
| MemoryManager | `agent/memory/manager.py` | MEMORY.md pattern: session transcripts, topic consolidation |

### Directory Structure
```
agent/
  kb/
    knowledge_base.py   (KnowledgeBase)
  memory/
    manager.py          (MemoryManager)
    MEMORY.md           (index — created at init)
    topics/             (successful_patterns.json, user_preferences.json, query_corrections.json)
    sessions/           ({session_id}.json files)
kb/
  architecture/
    CHANGELOG.md
  domain/
    CHANGELOG.md
  evaluation/
    CHANGELOG.md
  corrections/
    CHANGELOG.md
    corrections.json    (append-only)
tests/
  unit/
    test_knowledge_base.py
    test_memory_manager.py
```

### External Dependencies
- **Imports from**: `agent/models.py` (KBDocument, CorrectionEntry, SessionMemory)
- **External**: file system only — no network dependencies

### Key NFRs for This Unit
- `corrections.json`: append-only — never truncate
- All CHANGELOG.md files: append-only
- Session transcripts: write-once, never modified
- KB injection test: each document must pass parse/token-budget check before commit

---

## Unit 4: Evaluation Harness

**ID**: U4  
**Build Position**: 5th (independent; built after U1 since it calls AgentAPI)  
**Layer**: Evaluation

### Components
| Component | File | Responsibility |
|---|---|---|
| EvaluationHarness | `eval/harness.py` | Orchestrates full benchmark run |
| BenchmarkRunner | (internal) | Loads DAB queries; runs N trials per query via HTTP |
| ExactMatchScorer | (internal) | Numeric tolerance + string normalization scorer |
| LLMJudgeScorer | (internal) | GPT-4o judge: pass/fail + rationale |
| QueryTraceRecorder | (internal) | Writes traces to `results/traces/` |
| RegressionSuite | (internal) | Asserts pass@1 >= previous run |
| ScoreLog | (internal) | Append-only `results/score_log.jsonl` |

### Directory Structure
```
eval/
  harness.py            (EvaluationHarness — all sub-components internal)
  run_benchmark.py      (CLI: python -m eval.run_benchmark --trials N)
results/
  score_log.jsonl       (append-only)
  traces/               ({session_id}.json per query)
tests/
  unit/
    test_harness.py
    test_scorers.py
```

### External Dependencies
- **Calls**: `AgentAPI` `/query` endpoint (HTTP — treats agent as black box)
- **Imports from**: `agent/models.py` (BenchmarkResult, DABQuery, JudgeVerdict)
- **External**: `openai.AsyncOpenAI` (LLM judge call), `httpx` or `aiohttp` (agent API calls)

### Key NFRs for This Unit
- Score log: append-only JSON Lines — never overwritten
- Regression suite: fail-fast if pass@1 drops below previous run
- LLM judge: separate GPT-4o call with structured judge prompt; confidence threshold recorded

---

## Unit 5: Utilities & Adversarial Probes

**ID**: U5  
**Build Position**: 1st (no dependencies on other units)  
**Layer**: Utilities

### Components
| Component | File | Responsibility |
|---|---|---|
| SchemaIntrospector | `utils/schema_introspector.py` | Introspects all 4 DB types via MCP Toolbox; returns SchemaContext |
| MultiPassRetriever | `utils/multi_pass_retriever.py` | 3-pass vocabulary search over corrections log |
| JoinKeyUtils | `utils/join_key_utils.py` | Format detection, key transformation, SQL expression builder |
| BenchmarkWrapper | `utils/benchmark_wrapper.py` | Simplified Python API for running DAB query subsets |
| ProbeLibrary | `probes/probes.md` + `probes/probe_runner.py` | 15+ adversarial probes; ProbeRunner executes and records |

### Directory Structure
```
utils/
  schema_introspector.py
  multi_pass_retriever.py
  join_key_utils.py
  benchmark_wrapper.py
probes/
  probes.md               (probe definitions: query, category, expected failure, fix, score)
  probe_runner.py         (ProbeRunner: executes probe against live agent)
tests/
  unit/
    test_join_key_utils.py
    test_multi_pass_retriever.py
    test_schema_introspector.py
    test_probe_runner.py
```

### External Dependencies
- **Imports from**: `agent/models.py` (SchemaContext, DBSchema, CorrectionEntry, JoinKeyFormat)
- **External**: `aiohttp` (MCP Toolbox introspection calls), `agent/config.py` (MCP_TOOLBOX_URL)

### Key NFRs for This Unit
- JoinKeyUtils: pure functions, no side effects — fully property-based testable
- SchemaIntrospector: handles MCP Toolbox unavailability gracefully (returns empty schema, not exception)
- Probes: minimum 15 probes covering at least 3 of 4 failure categories
- ProbeRunner: records pre-fix and post-fix scores per probe

---

## Construction Sequence Summary

```
STEP 1  Create agent/models.py + agent/config.py  (shared infrastructure)
        Create tests/ directory structure

STEP 2  Build U5 — Utilities & Adversarial Probes
        (no unit dependencies; JoinKeyUtils especially needed early)

STEP 3  Build U2 — Multi-DB Execution Engine
        (imports JoinKeyUtils from U5; calls MCP Toolbox)

STEP 4  Build U1 — Agent Core & API
        (imports MultiDBEngine from U2; imports U5 utils; imports U3 KB/memory)
        Note: U3 interfaces must be defined before U1 code generation

STEP 5  Build U3 — Knowledge Base & Memory System
        (independent of U1/U2/U5 at runtime; U1 imports it)
        (can be built in parallel with U1 if interfaces are agreed upfront)

STEP 6  Build U4 — Evaluation Harness
        (calls AgentAPI via HTTP — U1 must be runnable before E2E eval tests)

STEP 7  Build integration tests (tests/integration/)
        (requires all units functional + MCP Toolbox running)
```
