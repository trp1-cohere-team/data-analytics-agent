# The Oracle Forge — Data Analytics Agent

> A production-grade ReAct-loop agent that answers natural language questions by querying
> four heterogeneous databases (PostgreSQL, MongoDB, DuckDB, SQLite) through MCP Toolbox,
> with automatic failure correction, knowledge-base-augmented context, code sandbox execution,
> real-time SSE streaming, and persistent session memory.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Team](#team)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the Stack](#running-the-stack)
- [API Reference](#api-reference)
- [Code Sandbox](#code-sandbox)
- [Streaming API](#streaming-api)
- [Testing](#testing)
- [Adversarial Probes](#adversarial-probes)
- [Benchmarking](#benchmarking)
- [Project Structure](#project-structure)
- [Live Server](#live-server)

---

## Overview

The Oracle Forge receives a natural language question via HTTP, decides which database(s)
to query using a ReAct reasoning loop backed by an LLM (via OpenRouter), executes the
queries through MCP Toolbox, and returns a structured answer with a confidence score and
full query trace.

**Key features:**

| Feature | Detail |
|---------|--------|
| Multi-database routing | PostgreSQL, MongoDB, DuckDB, SQLite — automatically selects the right DB |
| ReAct orchestration | Reason + Act loop, up to 10 iterations, confidence threshold 0.85 |
| Tiered correction engine | 5 strategies: rule-based first, LLM corrector as last resort |
| Code sandbox | Agent runs Python snippets in a sandboxed subprocess for data transformation |
| Streaming API | `POST /query/stream` emits real-time SSE events as the agent reasons |
| Knowledge base | 4-layer KB (architecture, domain, evaluation, corrections) injected into every request |
| Session memory | Per-session transcript with consolidation via MemoryManager |
| API key rotation | Automatically rotates OpenRouter keys on credit exhaustion (HTTP 402) |
| Rate limiting | 20 requests/minute per IP (slowapi) |
| Property-based testing | 15 Hypothesis PBT properties, all blocking |
| Adversarial probes | 15 probes across ROUTING, JOIN_KEY, SYNTAX, NULL_GUARD, CONFIDENCE |

---

## Architecture

```
                    HTTP :8000
          ┌───────────────────────────┐
          │  FastAPI  app.py          │
          │  POST /query              │
          │  POST /query/stream (SSE) │
          │  GET  /health             │
          └───────────┬───────────────┘
                      │
             ┌────────▼────────┐
             │  Orchestrator   │  ReAct loop
             │  react_loop.py  │  max 10 iters
             └─┬──────┬─────┬──┘  confidence ≥ 0.85
               │      │     │
    ┌──────────▼─┐ ┌──▼──┐ ┌▼──────────────────┐
    │  Context   │ │  KB │ │  CorrectionEngine  │
    │  Manager   │ │     │ │  5 strategies      │
    │  (3 layers)│ │     │ │  rule → LLM        │
    └──────┬─────┘ └─────┘ └────────────────────┘
           │
    ┌──────▼──────────────┬─────────────────────┐
    │   MultiDBEngine     │    Code Sandbox      │
    │   MCP Toolbox :5000 │    sandbox.py        │
    └──┬──────┬────┬──┬───┘    subprocess + AST  │
       │      │    │  │        5s timeout         │
  [postgres][mongo][duck][sqlite]  [Python snippet]
  orders  reviews analytics yelp   transform_data
```

### Data Routing

| Database | Type | Contents | When to use |
|----------|------|----------|-------------|
| PostgreSQL | Relational | Orders, customers, products, transactions | Structured transactional queries |
| MongoDB | Document | Reviews, unstructured business data | Text search, document queries |
| DuckDB | Analytical | Pre-computed aggregates, sentiment scores | Analytics, OLAP |
| SQLite | Relational | Yelp dataset — businesses, check-ins | Yelp-specific queries |

### Correction Strategy Order

```
1. rule_syntax     — ROWNUM→LIMIT, ISNULL→IS NULL, NVL→COALESCE
2. rule_join_key   — INTEGER↔PREFIXED_STRING↔UUID format transforms
3. rule_db_type    — reroute to correct database
4. rule_null_guard — add COALESCE guards for null fields
5. llm_corrector   — last resort: send error to LLM (only when all rules fail)
```

---

## Team

| Name | Role |
|------|------|
| Nurye | Driver |
| Kemeriya | Driver |
| Amare | Intelligence Officer |
| Ephrata | Intelligence Officer |
| Yohanis | Signal Corps |
| Addisu | Signal Corps |

---

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Docker + Docker Compose (for PostgreSQL, MongoDB, MCP Toolbox)
- An [OpenRouter](https://openrouter.ai) API key

### 1. Clone

```bash
git clone <repo-url>
cd data-analytics-agent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
# Single key
OPENROUTER_API_KEY=sk-or-your-key-here

# OR multiple keys for automatic rotation when one runs out of credits
OPENROUTER_API_KEYS=sk-or-key1,sk-or-key2,sk-or-key3

OPENROUTER_MODEL=openai/gpt-4o-mini   # cheaper for testing; use gpt-4o for production

POSTGRES_USER=oracle_forge
POSTGRES_PASSWORD=changeme
POSTGRES_DB=oracle_forge
MONGODB_URI=mongodb://localhost:27017
```

### 4. Start the database stack

```bash
docker compose -f docker-compose.mcp.yml up -d
```

This starts PostgreSQL (:5432), MongoDB (:27017), and MCP Toolbox (:5000).

### 5. Start the agent

```bash
uvicorn agent.api.app:app --host 0.0.0.0 --port 8000
```

### 6. Send a query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many orders were placed last month?", "session_id": "demo-001"}'
```

---

## Configuration

All settings are in `agent/config.py` and read from the environment (or `.env`).

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | `""` | Single OpenRouter API key |
| `OPENROUTER_API_KEYS` | `""` | Comma-separated keys — rotates on credit exhaustion |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API base URL |
| `OPENROUTER_MODEL` | `openai/gpt-4o` | Model ID passed to OpenRouter |
| `MCP_TOOLBOX_URL` | `http://localhost:5000` | MCP Toolbox endpoint |
| `MAX_RESULT_ROWS` | `1000` | Maximum rows returned by any single DB query |
| `AGENT_PORT` | `8000` | FastAPI listen port |
| `RATE_LIMIT` | `20/minute` | Per-IP rate limit |
| `MAX_REACT_ITERATIONS` | `10` | Maximum ReAct loop iterations per request |
| `CONFIDENCE_THRESHOLD` | `0.85` | Stop iterating when LLM confidence reaches this |
| `MAX_CORRECTION_ATTEMPTS` | `3` | Maximum correction attempts per failed query |
| `LAYER2_REFRESH_INTERVAL_S` | `60` | How often to reload KB documents (seconds) |
| `MEMORY_MAX_AGE_DAYS` | `7` | Session transcripts older than this are purged |
| `KB_DIR` | `kb` | Path to the knowledge base directory |

### API key rotation

When one OpenRouter key's credits are exhausted the agent receives HTTP 402. With
`OPENROUTER_API_KEYS` set, `KeyRotatingOpenAI` (`utils/key_rotator.py`) transparently
rotates to the next key and retries — the request succeeds without any error to the caller.
Rotation is also triggered by `RateLimitError` (HTTP 429). A `key_rotated` warning is
logged each time rotation occurs.

---

## Running the Stack

### MCP Toolbox (database abstraction layer)

MCP Toolbox reads `tools.yaml` and exposes four tools over HTTP:

```bash
# Start Toolbox with the project config
mcp-toolbox --config tools.yaml

# Verify it's running
curl http://localhost:5000/api/toolset
```

Tools exposed:

| Tool | Database | Operation |
|------|----------|-----------|
| `postgres_query` | PostgreSQL | SQL SELECT |
| `sqlite_query` | SQLite (Yelp) | SQL SELECT |
| `mongo_aggregate` | MongoDB | Aggregation pipeline |
| `duckdb_query` | DuckDB | Analytical SQL |

### Agent API

```bash
# Development (auto-reload)
uvicorn agent.api.app:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn agent.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok", "mcp_toolbox": "reachable"}
```

---

## API Reference

### `POST /query`

Submit a natural language question to the agent.

**Request:**

```json
{
  "question": "What is the average order value by product category?",
  "session_id": "optional-string-for-session-continuity"
}
```

**Response:**

```json
{
  "answer": "The average order value by category is: Electronics $342, Clothing $87, Books $24.",
  "confidence": 0.92,
  "session_id": "abc-123",
  "query_trace": [
    {
      "iteration": 1,
      "thought": "Need to query orders grouped by category.",
      "action": "postgres_query",
      "action_input": {"sql": "SELECT category, AVG(value) FROM orders GROUP BY category"},
      "observation": "[{category: Electronics, avg: 342.1}, ...]"
    }
  ]
}
```

**Error responses:**

| Status | Body | Cause |
|--------|------|-------|
| `429` | `{"error": "rate_limit_exceeded"}` | More than 20 req/min from same IP |
| `500` | `{"error": "query_failed", "message": "<ExceptionType>"}` | Unhandled internal error (no stack trace exposed) |

### `GET /health`

Returns MCP Toolbox liveness status.

```json
{"status": "ok", "mcp_toolbox": "reachable"}
```

### `GET /schema`

Returns the current cached database schema (all four databases).

---

## Code Sandbox

The agent can execute Python snippets to transform or extract data using the `transform_data` action.

**How it works:**

1. The LLM emits `{"action": "transform_data", "action_input": {"code": "...", "variables": {...}}}` in its ReAct JSON
2. `CodeSandbox.execute()` runs the snippet in a **child subprocess** with a 5-second hard timeout
3. An **AST pre-check** enforces a strict import whitelist before any subprocess is spawned
4. The result, captured stdout, and any error are returned to the orchestrator as an observation

**Allowed imports:** `json`, `re`, `math`, `datetime`, `collections`

**Example — agent-generated usage:**
```json
{
  "action": "transform_data",
  "action_input": {
    "code": "result = [r for r in rows if r['score'] > threshold]",
    "variables": {
      "rows": [{"id": 1, "score": 0.3}, {"id": 2, "score": 0.9}],
      "threshold": 0.5
    }
  }
}
```

**Output:**
```json
{"result": [{"id": 2, "score": 0.9}], "stdout": "", "error": null}
```

**Security constraints:**
- Code length capped at 4096 characters
- Non-whitelisted imports rejected at AST level (no subprocess spawned)
- Metadata-only logging — code content and variable values are never logged
- Temp script file always deleted in `finally` block

---

## Streaming API

`POST /query/stream` streams agent progress as **Server-Sent Events (SSE)** so you see each reasoning step in real time instead of waiting for the final answer.

**Endpoint:** `POST /query/stream`  
**Request body:** same as `POST /query`  
**Response:** `Content-Type: text/event-stream`

**Event types:**

| Event | Fields | When |
|-------|--------|------|
| `thought` | `iteration`, `action`, `confidence` | LLM picks next action |
| `action` | `iteration`, `tool`, `success` | Tool call completes |
| `final_answer` | `answer`, `confidence`, `session_id`, `iterations_used` | Agent finishes |
| `error` | `message` (exception type only) | Unhandled error mid-stream |

**Wire format (SSE):**
```
event: thought
data: {"type":"thought","iteration":1,"action":"postgres_query","confidence":0.72}

event: action
data: {"type":"action","iteration":1,"tool":"postgres_query","success":true}

event: final_answer
data: {"type":"final_answer","answer":"Revenue was $42,000.","confidence":0.91,"session_id":"abc-123","iterations_used":2}

```

**curl example:**
```bash
curl -N -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What is total revenue this quarter?", "session_id": "stream-001"}'
```

**Notes:**
- `POST /query` is 100% unchanged — streaming is purely additive
- Observation data (raw DB rows) is **not** streamed — only metadata
- Rate limit (20 req/min) applies to `/query/stream` as well

---

## Testing

All unit tests run without any external services — every database and LLM call is mocked.

### Unit tests — 399 tests, 16 test files

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run only property-based tests (15 blocking PBT properties)
python -m pytest tests/unit/ -v -k "PBT or self_consistency or round_trip"

# Run with coverage
python -m pytest tests/unit/ --cov=agent --cov=utils --cov-report=term-missing
```

**Test files:**

| File | Unit | Tests |
|------|------|-------|
| `test_api.py` | U1 — Agent API | API routes, rate limiting, error handling |
| `test_orchestrator.py` | U1 — Orchestrator | ReAct loop, iteration limits, confidence |
| `test_context_manager.py` | U1 — Context | 3-layer context assembly |
| `test_correction_engine.py` | U1 — Correction | 5 strategies, PBT round-trip |
| `test_execution_engine.py` | U2 — MultiDB | Per-DB dispatch, result merging |
| `test_mcp_client.py` | U2 — MCP Client | Tool calls, error classification |
| `test_knowledge_base.py` | U3 — KB | Document loading, token budget, PBT |
| `test_memory_manager.py` | U3 — Memory | Session lifecycle, PBT |
| `test_schema_introspector.py` | U5 — Schema | Introspection, timeout bulkhead |
| `test_join_key_utils.py` | U5 — Utils | Key format transforms, PBT |
| `test_multi_pass_retriever.py` | U5 — Utils | TF-IDF retrieval, PBT |
| `test_probe_runner.py` | U5 — Probes | Probe execution, scoring |
| `test_harness.py` | U4 — Eval | Benchmark pipeline, trial runner |
| `test_scorers.py` | U4 — Eval | ExactMatch, FuzzyMatch, PBT |
| `test_sandbox.py` | U6 — Sandbox | Execution, whitelist, timeout, error cases |
| `test_streaming.py` | U7 — Streaming | SSE format, run_stream(), /query/stream endpoint |

### Integration tests — 11 tests (require MCP Toolbox + agent running)

```bash
# Requires: MCP Toolbox on :5000, agent on :8000
python -m pytest tests/integration/ -v --timeout=120
```

Integration tests auto-skip when MCP Toolbox is not reachable.

### Security scan

```bash
safety check -r requirements.txt
```

---

## Adversarial Probes

The probe library (`probes/`) contains 15 adversarial probes that test failure modes
not covered by unit tests. Pass threshold: **≥ 80%** of probes must pass.

```bash
# Run all probes
python probes/probe_runner.py --agent-url http://localhost:8000

# Run one category
python probes/probe_runner.py --agent-url http://localhost:8000 --category ROUTING
```

**Probe categories:**

| Category | What it tests |
|----------|--------------|
| `ROUTING` | Agent routes to correct database (e.g., orders → PostgreSQL not MongoDB) |
| `JOIN_KEY` | Cross-DB join key format mismatches (INTEGER vs PREFIXED_STRING vs UUID) |
| `SYNTAX` | DB-specific syntax errors (ROWNUM, ISNULL, NVL) trigger correction |
| `NULL_GUARD` | Null values in aggregates handled with COALESCE |
| `CONFIDENCE` | Low-confidence answers are flagged, not silently returned |

---

## Benchmarking

The evaluation harness (`eval/`) runs the DataAgentBench (DAB) benchmark against the live agent.

```bash
# Run a quick single-trial benchmark (fast, good for smoke testing)
python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 1

# Run full 50-trial benchmark (slow — use multiple API keys)
python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 50

# Against the shared EC2 server
python -m eval.run_benchmark --agent-url http://10.0.6.41:8000 --trials 1
```

Results are written to `results/harness_score_log.json` and `eval/score_log.md`.

**Score history:**

| Run | Score | Notes |
|-----|-------|-------|
| Run 1 | 0.41 | Baseline — no KB, no corrections |
| Run 2 | 0.67 | Post KB injection (domain + architecture layers) |
| Run 3 | 0.84 | Post probe-driven corrections (ROUTING + JOIN_KEY fixes) |

**Cost guidance:**

| Model | Cost/1K tokens | Full DAB (54q × 50 trials) | Quick smoke test (1 trial) |
|-------|----------------|----------------------------|----------------------------|
| `openai/gpt-4o` | ~$5/1M | ~$60 | ~$1.20 |
| `openai/gpt-4o-mini` | ~$0.15/1M | ~$2 | ~$0.04 |

For testing, use `OPENROUTER_MODEL=openai/gpt-4o-mini` — scores are lower but the
pipeline behavior is identical. Switch to `gpt-4o` only for the final leaderboard run.

---

## Project Structure

```
data-analytics-agent/
│
├── agent/                      # Core agent source
│   ├── api/
│   │   ├── app.py              # FastAPI app + lifespan
│   │   └── middleware.py       # Security headers
│   ├── orchestrator/
│   │   └── react_loop.py       # ReAct loop (Orchestrator)
│   ├── context/                # 3-layer context assembly
│   ├── correction/             # CorrectionEngine (5 strategies)
│   ├── execution/              # MultiDBEngine + MCP client + CodeSandbox
│   ├── kb/                     # KnowledgeBase (reads kb/ dir)
│   ├── memory/                 # MemoryManager (session transcripts)
│   ├── models.py               # Pydantic models (all shared types)
│   ├── config.py               # Settings (pydantic-settings)
│   ├── AGENT.md                # Agent identity + system prompt context
│   └── tools.yaml              # MCP Toolbox config (agent copy)
│
├── utils/                      # Shared utilities
│   ├── schema_introspector.py  # Live schema fetch from MCP Toolbox
│   ├── join_key_utils.py       # Cross-DB join key format transforms
│   ├── multi_pass_retriever.py # TF-IDF KB document retrieval
│   ├── benchmark_wrapper.py    # Safe trial wrapper for eval harness
│   └── key_rotator.py          # KeyRotatingOpenAI — auto key rotation on HTTP 402
│
├── eval/                       # Evaluation harness
│   ├── harness.py              # EvaluationHarness + FailSafeTrialRunner
│   ├── run_benchmark.py        # CLI entry point for DAB benchmark
│   ├── score_log.md            # Human-readable score history
│   └── test_set.json           # 10 held-out queries with expected answers
│
├── probes/                     # Adversarial probe library
│   ├── probe_runner.py         # CLI runner — outputs pass/fail/score
│   └── probes.md               # Probe definitions (15 probes)
│
├── kb/                         # Knowledge base documents
│   ├── architecture/           # Schema overview, MCP Toolbox topology
│   ├── domain/                 # Routing rules, field glossary
│   ├── evaluation/             # Baseline queries, scoring rubric
│   └── corrections/            # Known failure patterns + fixes
│
├── tests/
│   ├── unit/                   # 399 unit tests (no external services)
│   └── integration/            # 11 integration tests (require running stack)
│
├── results/                    # Benchmark output
│   ├── dab_results.json        # Per-query DAB scores
│   ├── harness_score_log.json  # Score history (JSON)
│   └── pr_link.md              # DataAgentBench leaderboard PR link
│
├── signal/                     # Community engagement
│   ├── engagement_log.md       # Published articles log
│   └── community_participation.md  # Discord/LinkedIn/GitHub activity
│
├── aidlc-docs/                 # AI-DLC build documentation
│   ├── inception/              # Requirements, design, unit breakdown
│   ├── construction/           # Per-unit functional + NFR design
│   ├── aidlc-state.md          # Stage completion tracker
│   └── audit.md                # Full mob session approval log
│
├── planning/                   # Team operating system documents
│   ├── ai_dlc_playbook.md
│   ├── mob_session_log.md
│   └── release_readiness_checklist.md
│
├── tools.yaml                  # MCP Toolbox — data sources + tool definitions
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Project metadata + pytest config
└── .env.example                # Environment variable template
```

---

## Live Server

The agent is deployed on the shared EC2 instance:

**Base URL:** `http://10.0.6.41:8000`

```bash
# Health check
curl http://10.0.6.41:8000/health

# Query (blocking)
curl -X POST http://10.0.6.41:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top 5 products by revenue?", "session_id": "test-001"}'

# Streaming query (SSE — see events in real time)
curl -N -X POST http://10.0.6.41:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top 5 products by revenue?", "session_id": "stream-001"}'

# Schema
curl http://10.0.6.41:8000/schema

# Run benchmark against live server
python -m eval.run_benchmark --agent-url http://10.0.6.41:8000 --trials 1

# Run probes against live server
python probes/probe_runner.py --agent-url http://10.0.6.41:8000
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API framework | FastAPI 0.111 + uvicorn |
| Data validation | Pydantic v2 + pydantic-settings |
| LLM client | openai SDK (OpenRouter backend) |
| DB abstraction | MCP Toolbox (postgres, mongo, duckdb, sqlite) |
| HTTP client | aiohttp |
| Rate limiting | slowapi |
| Testing | pytest + pytest-asyncio |
| Property-based testing | Hypothesis |
| Security scanning | safety |
| Analytical DB | DuckDB 0.10 |
