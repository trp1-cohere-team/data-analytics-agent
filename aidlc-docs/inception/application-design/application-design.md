# Application Design
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Status**: APPROVED  
**Architecture**: Layered (packaging) + ReAct loop (orchestrator control flow)

---

## 1. Architecture Overview

The Oracle Forge is a production-grade data analytics agent that translates natural language questions into structured queries across heterogeneous databases, self-corrects execution failures, and benchmarks measurable improvement over time.

### Two-Process Deployment

```
┌─────────────────────────────────────────────────────┐
│  Process 1: FastAPI Agent Server (agent/)            │
│                                                      │
│   AgentAPI → Orchestrator → MultiDBEngine            │
│              ContextManager   CorrectionEngine       │
│              KnowledgeBase    MemoryManager          │
│              EvaluationHarness                       │
│                                                      │
│   Port: 8000 (configurable)                          │
└──────────────────────────┬──────────────────────────┘
                           │ HTTP localhost:5000
                           │ /v1/tools/{tool_name}
┌──────────────────────────▼──────────────────────────┐
│  Process 2: MCP Toolbox for Databases               │
│                                                      │
│   tools.yaml defines connections:                    │
│     postgres_query   → PostgreSQL                    │
│     sqlite_query     → SQLite                        │
│     mongodb_aggregate→ MongoDB                       │
│     duckdb_query     → DuckDB                        │
└─────────────────────────────────────────────────────┘
```

### Control Flow Inside the Agent

```
HTTP Request
     │
     ▼
[AgentAPI]          ← FastAPI, Pydantic, slowapi, security headers
     │ run()
     ▼
[Orchestrator]      ← ReAct loop (max 10 iterations)
  ┌─ think() ──────────────────────────────→ LLM (OpenRouter/GPT-4o)
  ├─ act()
  │    ├─ query_database ────────────────→ [MultiDBEngine]
  │    │                                        └─ MCP Toolbox (HTTP)
  │    ├─ search_kb ──────────────────────→ [MultiPassRetriever]
  │    ├─ extract_from_text ──────────────→ LLM (sub-call)
  │    └─ resolve_join_keys ─────────────→ [JoinKeyUtils]
  └─ observe() → update state → loop or terminate
     │
     │ [on failure]
     ▼
[CorrectionEngine]  ← classify → cheapest fix → retry (max 3)
     │ [always]
     ▼
[KnowledgeBase]     ← append correction entry
     │
     ▼
[AgentAPI]          ← build QueryResponse
     │
     ▼
HTTP Response
```

---

## 2. Layered Architecture

### Layer Map

```
LAYER: API
  AgentAPI                        agent/api/app.py

LAYER: ORCHESTRATION
  Orchestrator (ReAct loop)       agent/orchestrator/react_loop.py
  ContextManager                  agent/context/manager.py
  CorrectionEngine                agent/correction/engine.py

LAYER: EXECUTION
  MultiDBEngine                   agent/execution/engine.py
    QueryRouter                   (internal to engine.py)
    PostgreSQLConnector           (internal)
    SQLiteConnector               (internal)
    MongoDBConnector              (internal)
    DuckDBConnector               (internal)
    JoinKeyResolver               (delegates to utils/join_key_utils.py)
    ResultMerger                  (internal)

LAYER: KNOWLEDGE
  KnowledgeBase                   agent/kb/knowledge_base.py
  MemoryManager                   agent/memory/manager.py

LAYER: EVALUATION
  EvaluationHarness               eval/harness.py
    BenchmarkRunner               (internal)
    ExactMatchScorer              (internal)
    LLMJudgeScorer                (internal)
    QueryTraceRecorder            (internal)
    RegressionSuite               (internal)
    ScoreLog                      (internal)

LAYER: UTILITIES
  SchemaIntrospector              utils/schema_introspector.py
  MultiPassRetriever              utils/multi_pass_retriever.py
  JoinKeyUtils                    utils/join_key_utils.py
  BenchmarkWrapper                utils/benchmark_wrapper.py
  ProbeLibrary                    probes/probes.md + probes/probe_runner.py
```

---

## 3. Three-Layer Context Architecture

| Layer | Content | Load Trigger | Reload Trigger | Cache Scope |
|---|---|---|---|---|
| Layer 1 — Schema | DB schemas from all 4 connected DBs | Server startup (once) | Never | Process-global, permanent |
| Layer 2 — Domain KB | Architecture + domain + join key glossary documents | Server startup (once) | File mtime change (checked every 60s) | Process-global, hot |
| Layer 3 — Corrections | Last 50 corrections from corrections.json + session memory | Per session start | Never (fresh each time) | Session-scoped, never cached |

**Rationale**: Each layer's cache policy matches its actual change frequency. Schema changes require server restart anyway. KB documents are edited occasionally. Corrections accumulate continuously and must always reflect the latest state for the session.

---

## 4. ReAct Loop Design

```
State: ReactState
  ├── query: str
  ├── iteration: int (max 10)
  ├── history: list[TraceStep]
  └── terminated: bool

Each iteration:
  think(state) → Thought
    ├── reasoning: str
    ├── chosen_action: str  (one of: query_database, search_kb,
    │                         extract_from_text, resolve_join_keys, FINAL_ANSWER)
    └── action_input: dict

  act(thought, context) → Observation
    ├── query_database    → ExecutionService.execute(QueryPlan)
    ├── search_kb         → MultiPassRetriever.retrieve_corrections(query, corrections)
    ├── extract_from_text → LLM sub-call with text extraction prompt
    ├── resolve_join_keys → JoinKeyUtils.detect_format + build_transform_expression
    └── FINAL_ANSWER      → terminate loop

  observe(observation, state) → updated ReactState
    ├── append TraceStep(thought, action, observation) to history
    ├── if action == FINAL_ANSWER: set terminated = True
    └── if iteration >= max_iterations: set terminated = True

Termination: FINAL_ANSWER action OR iteration limit reached
Confidence: extracted from LLM output; threshold 0.85 triggers FINAL_ANSWER preference
```

---

## 5. Tiered Correction Design

```
ExecutionFailure received
         │
         ▼
classify_failure(failure) → FailureType
         │
    ┌────┴──────────────────────────────────────────────────────┐
    │                                                           │
SYNTAX_ERROR         JOIN_KEY_MISMATCH    WRONG_DB_TYPE    DATA_QUALITY
    │                       │                   │               │
fix_syntax_error()    fix_join_key()    fix_wrong_db_type()  fix_data_quality()
  rule-based           JoinKeyUtils       reroute plan        add COALESCE
  rewriter            transform           (no LLM)           (no LLM)
  (no LLM)            (no LLM)
    │                       │                   │               │
    └─────────────────────┬─┴───────────────────┘               │
                          │                                     │
                    [if all fail after 2 attempts]              │
                          │                                     │
                          ▼                                     │
                   UNKNOWN / llm_correct()  ←───────────────────┘
                     Last resort LLM call
                     (attempt 3 only)
                          │
                    [if still fails]
                          │
                          ▼
                   CorrectionExhausted raised
                   (logged, returned as low-confidence answer)
```

All correction attempts (success or failure) → logged to `kb/corrections/corrections.json`.

---

## 6. Knowledge Base Structure

```
kb/
  architecture/
    CHANGELOG.md
    system-overview.md          (agent architecture, component roles)
    mcp-toolbox-integration.md  (tools.yaml, HTTP protocol, tool names)
    react-loop-design.md        (think/act/observe pattern)
  domain/
    CHANGELOG.md
    join-key-glossary.md        (cross-DB key format conventions)
    database-schemas.md         (human-readable schema summaries)
    query-patterns.md           (common query shapes per DB type)
  evaluation/
    CHANGELOG.md
    benchmark-design.md         (DAB dataset structure, scoring method)
    probe-results.md            (adversarial probe outcomes)
  corrections/
    CHANGELOG.md
    corrections.json            (append-only log of all correction attempts)
```

Each document passes the **KB injection test** before commit: it must be fully parseable as schema context by the ContextManager (no truncation, no encoding errors, under token budget).

---

## 7. Memory System Structure

```
agent/memory/
  MEMORY.md                       (index: one line per topic file)
  topics/
    successful_patterns.json      (query patterns that reliably work)
    user_preferences.json         (session-level preferences if detected)
    query_corrections.json        (corrections that improved accuracy)
  sessions/
    {session_id}.json             (full QueryTrace per session)
```

**autoDream consolidation**: Sessions older than 7 days are read, patterns extracted, merged into topic files, and raw session files deleted. Prevents unbounded growth.

---

## 8. MCP Toolbox Integration

| Tool Name | DB Type | Protocol |
|---|---|---|
| `postgres_query` | PostgreSQL | HTTP POST `/v1/tools/postgres_query` |
| `sqlite_query` | SQLite | HTTP POST `/v1/tools/sqlite_query` |
| `mongodb_aggregate` | MongoDB | HTTP POST `/v1/tools/mongodb_aggregate` |
| `duckdb_query` | DuckDB | HTTP POST `/v1/tools/duckdb_query` |

- MCP Toolbox runs as an independent binary, configured by `tools.yaml`
- Agent is a pure HTTP client — no MCP SDK embedded in agent code
- All calls are async (aiohttp), 30s timeout per sub-query
- Errors from MCP Toolbox are wrapped as `ExecutionFailure` — never bubble to API response as raw exceptions

---

## 9. Security Design

Enforced per Security Baseline extension (all 15 rules, blocking):

| Area | Implementation |
|---|---|
| Input validation | Pydantic `QueryRequest` with field constraints |
| Rate limiting | `slowapi` on `/query` endpoint |
| HTTP security headers | Middleware: X-Content-Type-Options, X-Frame-Options, CSP |
| Error policy | Global handler: generic `{"error": "query_failed"}` — no stack traces |
| DB connections | Encrypted (TLS) for PostgreSQL; parameterized queries only |
| LLM API key | Environment variable only — never in code or logs |
| Dependencies | Pinned in `requirements.txt`; weekly `safety check` in CI |
| Injection prevention | Schema context passed as structured data, not raw string interpolation |

---

## 10. Directory Structure

```
data-analytics-agent/              ← workspace root (application code)
  agent/
    api/
      app.py                       (AgentAPI)
    orchestrator/
      react_loop.py                (Orchestrator)
    context/
      manager.py                   (ContextManager)
    correction/
      engine.py                    (CorrectionEngine)
    execution/
      engine.py                    (MultiDBEngine)
    kb/
      knowledge_base.py            (KnowledgeBase)
    memory/
      manager.py                   (MemoryManager)
      MEMORY.md
      topics/
      sessions/
  eval/
    harness.py                     (EvaluationHarness)
    run_benchmark.py               (CLI entry point)
  utils/
    schema_introspector.py
    multi_pass_retriever.py
    join_key_utils.py
    benchmark_wrapper.py
  probes/
    probes.md
    probe_runner.py
  kb/
    architecture/
    domain/
    evaluation/
    corrections/
  results/
    score_log.jsonl
    traces/
  planning/
    AGENT.md                       (agent context file)
  signal/
    (benchmark signal files)
  tools.yaml                       (MCP Toolbox configuration)
  requirements.txt
  pyproject.toml
  aidlc-docs/                      ← documentation only
```

---

## 11. Design Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Agent ↔ MCP Toolbox relationship | Two separate processes (HTTP) | MCP Toolbox is an independent binary; clean separation; swappable |
| Context layer loading | Three-way frequency split | Matches each layer's actual change rate; avoids unnecessary reloads |
| Agent control flow pattern | Layered architecture + ReAct loop | Layers = packaging (navigability); ReAct = runtime control (flexibility) |
| Failure correction strategy | Tiered: classify → cheapest fix → LLM last resort | Avoids expensive LLM calls for 4 of 5 failure types; faster and cheaper |
| LLM backbone | OpenRouter → GPT-4o | Follows challenge specification; `openai` SDK with `base_url` override |
| Memory storage | JSON files (MEMORY.md pattern) | Matches challenge requirement; persistent, inspectable, no DB dependency |
| Scoring | Exact match + LLM-as-judge | Exact match for precision; judge for semantic equivalence on misses |
| Security | 15 blocking rules enforced | User opted in; all rules applicable to a production HTTP API |
