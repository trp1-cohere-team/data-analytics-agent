# Components
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Architecture**: Layered (packaging) + ReAct loop (orchestrator control flow)

---

## Component Map

```
LAYER: API
  AgentAPI

LAYER: ORCHESTRATION
  Orchestrator (ReAct loop)
  ContextManager
  CorrectionEngine

LAYER: EXECUTION
  MultiDBEngine
    QueryRouter
    PostgreSQLConnector
    SQLiteConnector
    MongoDBConnector
    DuckDBConnector
    JoinKeyResolver
    ResultMerger

LAYER: KNOWLEDGE
  KnowledgeBase
  MemoryManager

LAYER: EVALUATION
  EvaluationHarness
    BenchmarkRunner
    ExactMatchScorer
    LLMJudgeScorer
    QueryTraceRecorder
    RegressionSuite
    ScoreLog

LAYER: UTILITIES
  SchemaIntrospector
  MultiPassRetriever
  JoinKeyUtils
  BenchmarkWrapper
  ProbeLibrary
```

---

## Component 1: AgentAPI

**Unit**: U1 — Agent Core & API  
**Layer**: API

### Responsibility
The HTTP interface to the agent. Accepts natural language queries, validates inputs, enforces security policies, manages sessions, and returns structured responses. Delegates all query processing to the Orchestrator.

### Interfaces
- **Inbound**: HTTP POST `/query`, GET `/health`, GET `/schema`
- **Outbound**: Calls `Orchestrator.run(query, session_id, context)`

### Key Properties
- Framework: FastAPI (async)
- Input validation: Pydantic models (`QueryRequest`, `QueryResponse`)
- Security: rate limiting (slowapi), HTTP security headers middleware, global error handler
- Session: generates UUID session_id per request
- Error policy: returns generic `{"error": "query_failed", "message": "..."}` — never exposes internals

---

## Component 2: Orchestrator

**Unit**: U1 — Agent Core & API  
**Layer**: Orchestration

### Responsibility
The agent's brain. Implements the ReAct (Reason + Act) loop: given a query and loaded context, iterates through think → act → observe cycles until a confident answer is reached or the maximum iteration limit is hit. Decides which tools to call (DB queries, KB lookups, text extraction), assembles the final response, and delegates execution failures to the CorrectionEngine.

### Interfaces
- **Inbound**: Called by AgentAPI with `(query, session_id, context_bundle)`
- **Outbound**: Calls `ContextManager`, `MultiDBEngine`, `CorrectionEngine`, LLM client (OpenRouter → GPT-4o)

### Key Properties
- LLM client: `openai.AsyncOpenAI` with `base_url=OPENROUTER_BASE_URL`, `model="openai/gpt-4o"`
- ReAct loop: max 10 iterations; terminates on `FINAL_ANSWER` action or confidence ≥ 0.85
- Tool definitions passed to LLM: `query_database`, `search_kb`, `extract_from_text`, `resolve_join_keys`
- Trace: records every iteration (thought, action, observation) as `QueryTrace` object

---

## Component 3: ContextManager

**Unit**: U1 — Agent Core & API  
**Layer**: Orchestration

### Responsibility
Assembles and manages the three context layers, each with a different loading lifecycle:

| Layer | Content | Lifecycle |
|---|---|---|
| Layer 1 — Schema | DB schemas for all connected databases | Load once at server startup; permanent in-memory cache |
| Layer 2 — Domain KB | KB v1+v2 documents (architecture, domain, join key glossary) | Load once per server process; reload triggered by file mtime change |
| Layer 3 — Corrections | KB v3 corrections log entries | Load once per session start; never cached across sessions |

### Interfaces
- **Inbound**: Called by Orchestrator at session start; called by AgentAPI at startup for Layer 1
- **Outbound**: Reads from `kb/` directory; calls `SchemaIntrospector` for Layer 1

### Key Properties
- Layer 1 is loaded by `SchemaIntrospector` at startup and injected into `ContextManager` cache
- Layer 2 watches file mtimes; `asyncio` background task checks every 60s
- Layer 3 reads `kb/corrections/corrections.json` fresh at each session start
- Output: `ContextBundle(schema_ctx, domain_ctx, corrections_ctx)` dataclass

---

## Component 4: CorrectionEngine

**Unit**: U1 — Agent Core & API  
**Layer**: Orchestration

### Responsibility
Implements tiered failure correction. When the MultiDBEngine reports an execution failure, the CorrectionEngine classifies the failure type and applies the cheapest sufficient fix. Three of the four correction strategies require no LLM call. The LLM corrector is invoked only when all cheaper strategies are exhausted.

### Failure Types and Fix Strategies

| Failure Type | Detection Signal | Fix Strategy | LLM Needed? |
|---|---|---|---|
| Syntax error | DB driver exception with syntax keyword | Rewrite query syntax using rule-based transformer | No |
| Join key mismatch | Column type mismatch on JOIN / empty result on expected join | JoinKeyResolver reformat | No |
| Wrong DB type | Query dialect tokens incompatible with target DB | Reroute to correct DB type | No |
| Data quality / missing field | Null result where non-null expected | Add NULL handling / fallback aggregation | No |
| Unknown / complex | All above strategies exhausted | LLM corrector: send error + original query → get corrected query | Yes |

### Interfaces
- **Inbound**: Called by Orchestrator with `(failure: ExecutionFailure, original_query: str, context: ContextBundle)`
- **Outbound**: Calls `MultiDBEngine` with corrected query; optionally calls LLM client

### Key Properties
- Max 3 correction attempts total; raises `CorrectionExhausted` after 3 failures
- Every correction attempt logged to `kb/corrections/` (failure type, fix applied, outcome)

---

## Component 5: MultiDBEngine

**Unit**: U2 — Multi-DB Execution Engine  
**Layer**: Execution

### Responsibility
Routes and executes database queries across PostgreSQL, SQLite, MongoDB, and DuckDB. Translates query plans from the Orchestrator into DB-specific query dialects, executes them via MCP Toolbox (HTTP calls to localhost:5000), merges cross-DB results, and resolves join key format mismatches before merge.

### Sub-components

| Sub-component | Responsibility |
|---|---|
| QueryRouter | Reads `db_type` from query plan; dispatches to correct connector |
| PostgreSQLConnector | Translates to SQL; calls MCP Toolbox `postgres_query` tool |
| SQLiteConnector | Translates to SQL; calls MCP Toolbox `sqlite_query` tool |
| MongoDBConnector | Translates to aggregation pipeline; calls MCP Toolbox `mongodb_aggregate` tool |
| DuckDBConnector | Translates to analytical SQL; calls MCP Toolbox `duckdb_query` tool |
| JoinKeyResolver | Detects format mismatch between join keys; applies transformation (integer ↔ "CUST-NNNNN" etc.) |
| ResultMerger | Merges results from multiple DB queries into a single result set |

### Interfaces
- **Inbound**: Called by Orchestrator with `QueryPlan` (list of sub-queries, each with `db_type`, `query`, `join_key_info`)
- **Outbound**: HTTP calls to MCP Toolbox at `http://localhost:5000/v1/tools/{tool_name}`

### Key Properties
- MCP Toolbox is a separate process; this component is a pure HTTP client
- All DB calls are async (aiohttp)
- Errors returned as `ExecutionFailure(type, message, raw_error)` — never raised to API layer directly

---

## Component 6: KnowledgeBase

**Unit**: U3 — Knowledge Base & Memory System  
**Layer**: Knowledge

### Responsibility
Manages the KB file system. Provides read access to architecture, domain, and evaluation documents. Provides write access to the corrections log. Maintains CHANGELOG.md for each KB subdirectory. Runs injection tests to verify KB document quality.

### Directory Structure Managed
```
kb/
  architecture/   (CHANGELOG.md + *.md documents)
  domain/         (CHANGELOG.md + *.md documents)
  evaluation/     (CHANGELOG.md + *.md documents)
  corrections/    (CHANGELOG.md + corrections.json)
```

### Interfaces
- **Inbound**: Called by ContextManager (read), Orchestrator (append correction), EvaluationHarness (read evaluation docs)
- **Outbound**: File system reads/writes only

---

## Component 7: MemoryManager

**Unit**: U3 — Knowledge Base & Memory System  
**Layer**: Knowledge

### Responsibility
Implements the MEMORY.md pattern (from Claude Code architecture, Layer 3). Manages interaction memory as JSON files: an index file (`MEMORY.md`) pointing to topic files (`memory/topics/*.json`) and session transcripts (`memory/sessions/*.json`). Implements autoDream consolidation: compresses sessions older than N days into topic summary files.

### Directory Structure Managed
```
agent/memory/
  MEMORY.md               (index: pointers to topic files)
  topics/
    successful_patterns.json
    user_preferences.json
    query_corrections.json
  sessions/
    {session_id}.json
```

### Interfaces
- **Inbound**: Called by ContextManager (load Layer 3 per session), Orchestrator (write session transcript)
- **Outbound**: File system reads/writes only

---

## Component 8: EvaluationHarness

**Unit**: U4 — Evaluation Harness  
**Layer**: Evaluation

### Responsibility
Runs the agent against DAB queries, scores results, records traces, and maintains the score log showing measurable improvement across runs.

### Sub-components

| Sub-component | Responsibility |
|---|---|
| BenchmarkRunner | Loads DAB query set; runs agent N trials per query; collects raw results |
| ExactMatchScorer | Compares result to expected; numeric tolerance 1e-4; string normalization |
| LLMJudgeScorer | Second LLM call (GPT-4o) with judge prompt; returns pass/fail + rationale |
| QueryTraceRecorder | Serializes every ReAct iteration to JSON; stores in `results/traces/` |
| RegressionSuite | Runs agent against held-out test set; asserts no score regression vs previous run |
| ScoreLog | Append-only JSON Lines file; one entry per benchmark run with timestamp and scores |

### Interfaces
- **Inbound**: CLI (`python -m eval.run_benchmark --trials N`) or called by BenchmarkWrapper utility
- **Outbound**: Calls AgentAPI `/query` endpoint; writes to `results/`

---

## Component 9: SharedUtils

**Unit**: U5 — Utilities & Adversarial Probes  
**Layer**: Utilities

### Modules

| Module | Responsibility |
|---|---|
| SchemaIntrospector | Auto-introspects all 4 DB types; returns `SchemaContext` for ContextManager Layer 1 |
| MultiPassRetriever | Runs 3 vocabulary passes over corrections log; deduplicates; returns ranked matches |
| JoinKeyUtils | Format detection (integer / prefixed string / UUID / composite); transformation functions |
| BenchmarkWrapper | Simplified Python API for running subsets of DAB queries against any agent |

---

## Component 10: ProbeLibrary

**Unit**: U5 — Utilities & Adversarial Probes  
**Layer**: Utilities

### Responsibility
Stores 15+ adversarial probes in `probes/probes.md`. Each probe documents: query text, failure category, expected failure mode, observed agent response, fix applied, post-fix score. Includes a `ProbeRunner` that executes a probe against the live agent and records results.

### Failure Categories Covered (minimum 3 of 4)
1. Multi-database routing failure
2. Ill-formatted join key mismatch
3. Unstructured text extraction failure
4. Domain knowledge gap
