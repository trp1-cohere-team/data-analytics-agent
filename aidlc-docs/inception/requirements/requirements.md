# Requirements Document
# The Oracle Forge — Data Analytics Agent

**Version**: 1.0  
**Date**: 2026-04-11  
**Status**: Approved

---

## Intent Analysis

| Field | Value |
|---|---|
| User Request | Build a production-grade data analytics agent based on The Oracle Forge challenge (Weeks 8-9) |
| Request Type | New Project (Greenfield) |
| Scope Estimate | System-wide — multi-component, multi-database, multi-layer |
| Complexity Estimate | Complex — multiple engineering challenges, benchmark evaluation, strict deadlines |

---

## Key Decisions (from Requirements Questions)

| Decision | Choice | Rationale |
|---|---|---|
| LLM Backbone | OpenRouter → GPT-4o (primary) | Team has OpenRouter access; multi-LLM fallback possible |
| Programming Language | Python | Best DAB ecosystem support; standard for data/ML work |
| Database Support | All 4: PostgreSQL, SQLite, MongoDB, DuckDB | Full DAB coverage from start (interim submission) |
| Agent Interface | FastAPI HTTP server | REST interface, easy MCP integration, production-ready |
| Evaluation Scoring | Exact match + LLM-as-judge (both) | Exact match for numeric/structured; LLM-as-judge for ambiguous |
| Interaction Memory | JSON files (MEMORY.md pattern) | Mirrors Claude Code architecture; documented in KB v1 |
| Infrastructure | Local for now (no shared server yet) | Develop locally, deploy to shared server when available |
| Dataset Priority | Yelp first | Multi-source, nested JSON — mirrors full DAB problem space |
| Security Extension | ENABLED (blocking) | Production-grade requirement per challenge |
| PBT Extension | ENABLED (blocking) | Business logic, data transformations, serialization present |

---

## Functional Requirements

### FR-01: Natural Language Query Interface
The agent MUST accept natural language questions from users and translate them into executable queries against one or more databases.
- Input format: `{question: str, available_databases: list, schema_info: dict}`
- Output format: `{answer: any, query_trace: list, confidence: float}`
- API endpoint: `POST /query` on FastAPI server

### FR-02: Multi-Database Execution Engine
The agent MUST support querying all four database types in the same session:
- **PostgreSQL** — relational SQL (asyncpg or psycopg2)
- **SQLite** — embedded relational SQL (sqlite3)
- **MongoDB** — document store (motor/pymongo with aggregation pipeline support)
- **DuckDB** — analytical SQL (duckdb Python client)

The agent MUST route sub-queries to the correct database type and merge results correctly.

### FR-03: Three-Layer Context Architecture
The agent MUST implement at minimum three context layers populated before answering:

**Layer 1 — Schema & Metadata Knowledge**
- Database schemas for all connected databases
- Table/collection descriptions, column types, relationships
- Populated at session start via schema introspection tools
- Stored in: `agent/context/schema/`

**Layer 2 — Institutional & Domain Knowledge**
- Business term definitions (e.g., "revenue", "churn", "active customer")
- Authoritative vs deprecated table mappings
- Cross-database entity ID format glossary (ill-formatted join key registry)
- Unstructured field inventory (fields requiring text extraction)
- Source: `kb/domain/` Knowledge Base documents

**Layer 3 — Interaction Memory**
- Corrections received from users
- Successful query patterns (cached for reuse)
- User preferences across sessions
- Implementation: JSON files following MEMORY.md pattern (index → topic files)
- Stored in: `agent/memory/`

### FR-04: Self-Correcting Execution Loop
The agent MUST detect execution failures and recover without surfacing raw errors to the user:
- Detect failure type: query syntax error, join key format mismatch, wrong database type, data quality issue
- Attempt at least 3 recovery strategies before escalating
- Log every failure with diagnosis to `kb/corrections/` (corrections log)
- Return a degraded-but-safe response if all recovery attempts fail

### FR-05: Ill-Formatted Join Key Resolution
The agent MUST detect and resolve cross-database entity key format mismatches:
- Example: `1234` (PostgreSQL integer) ↔ `"CUST-01234"` (MongoDB string)
- Resolution logic based on KB domain join key glossary
- No assumption of clean schema

### FR-06: Unstructured Text Transformation
The agent MUST extract structured facts from unstructured text fields before using them in calculations:
- Support fields: support notes, review text, product descriptions, free-text comments
- Extraction via LLM sub-call (GPT-4o via OpenRouter)
- Cache extraction results to avoid redundant LLM calls

### FR-07: Evaluation Harness
The agent MUST include an evaluation harness that:
- Runs the agent against DAB queries (54 total, 50 trials each for benchmark)
- Records query trace (every tool call, DB query, intermediate result)
- Scores results using pass@1 with:
  - Exact match (numeric tolerance for floats)
  - LLM-as-judge for ambiguous/complex answers
- Produces a score log showing measurable improvement between runs
- Runs a regression suite against a held-out test set

### FR-08: LLM Knowledge Base (KB)
The agent MUST maintain a structured Knowledge Base with four subdirectories:
- `kb/architecture/` — Agent architecture docs (Claude Code memory, OpenAI 6-layer context)
- `kb/domain/` — DAB schema descriptions, join key glossary, domain term definitions
- `kb/evaluation/` — DAB query format, scoring method, harness schema
- `kb/corrections/` — Running failure log: `[query failed] → [what was wrong] → [correct approach]`

Each KB subdirectory MUST have a `CHANGELOG.md` and injection test evidence.

### FR-09: Adversarial Probe Library
The agent MUST be tested against ≥15 adversarial probes covering ≥3 of DAB's 4 failure categories:
1. Multi-database routing failure
2. Ill-formatted key mismatch
3. Unstructured text extraction failure
4. Domain knowledge gap

### FR-10: Repository Structure
The codebase MUST follow the required directory structure:
```
data-analytics-agent/
├── agent/          # Agent source, AGENT.md, MCP tools.yaml
├── kb/             # Knowledge Base (architecture, domain, evaluation, corrections)
├── eval/           # Evaluation harness source + score logs
├── planning/       # AI-DLC Inception documents + mob session approval records
├── utils/          # Shared utility library (≥3 documented modules)
├── signal/         # Engagement log, community participation log
├── probes/         # Adversarial probe library (probes.md)
├── results/        # DAB results JSON, harness score log
└── README.md       # Team members, architecture diagram, setup instructions
```

### FR-11: MCP Toolbox Integration
The agent MUST use Google MCP Toolbox for Databases:
- `agent/mcp/tools.yaml` defines connections to all 4 database types
- Agent calls tools via MCP protocol (no raw per-DB drivers in agent logic)
- Toolbox runs on `http://localhost:5000`

---

## Non-Functional Requirements

### NFR-01: Performance
- Agent must return a response to a single-database query in < 30 seconds
- Agent must return a response to a multi-database query in < 60 seconds
- Evaluation harness must process ≥1 trial per minute

### NFR-02: Reliability
- Agent MUST handle execution failures gracefully (no unhandled exceptions surfaced to user)
- Self-correction loop MUST attempt ≥3 recovery strategies
- Global error handler MUST be present at FastAPI application entry point (SECURITY-15)

### NFR-03: Observability
- Structured logging MUST be configured (Python `structlog` or `logging` with JSON formatter) — SECURITY-03
- Every query execution MUST produce an auditable trace (tool calls, queries, results)
- Score logs MUST be append-only (never overwritten)

### NFR-04: Security (ENABLED — blocking)
- All database connections MUST use encrypted connections (SECURITY-01)
- API keys and secrets MUST be stored in `.env` file / environment variables — never hardcoded (SECURITY-12)
- All API parameters MUST be validated with Pydantic models (SECURITY-05)
- FastAPI MUST include HTTP security headers middleware (SECURITY-04)
- Rate limiting MUST be applied to public-facing `/query` endpoint (SECURITY-11)
- Error responses MUST NOT expose stack traces or internal details (SECURITY-09)
- Dependencies MUST be pinned in `requirements.txt` with a `requirements.lock` or `pip-compile` output (SECURITY-10)

### NFR-05: Property-Based Testing (ENABLED — blocking)
- Hypothesis framework MUST be selected and configured (PBT-09)
- Round-trip properties MUST be tested for: JSON serialization/deserialization of query results and KB documents (PBT-02)
- Invariant properties MUST be tested for: query trace completeness, score calculation correctness (PBT-03)
- Idempotency MUST be tested for: schema introspection (same schema on repeat calls), KB document loading (PBT-04)
- Generator quality: custom Hypothesis strategies for `DABQuery`, `QueryResult`, `ContextLayer` domain objects (PBT-07)
- All PBT MUST support shrinking and seed-based reproducibility (PBT-08)
- PBT MUST complement (not replace) example-based tests (PBT-10)

### NFR-06: Reproducibility
- Any team member MUST be able to re-deploy from a clean clone using README instructions
- All dependencies pinned; `requirements.txt` committed

### NFR-07: Benchmark Compliance
- Results JSON MUST conform to DAB submission format (54 queries, 50 trials each)
- GitHub PR to `ucbepic/DataAgentBench` with `AGENT.md` and results JSON
- PR title: `[Team Name] — TRP1 FDE Programme, April 2026`

---

## Deadlines

| Milestone | Date | Requirements |
|---|---|---|
| Interim Submission | 2026-04-15 21:00 UTC | GitHub repo + PDF report. Agent running locally on ≥2 DB types, KB v1+v2, eval harness baseline, planning/ with AI-DLC Inception doc |
| Final Submission | 2026-04-18 21:00 UTC | + KB v3, probes/ (15+ probes), results/ (DAB JSON), signal/ (articles + engagement log), demo video (≤8 min) |

---

## Architecture Overview

```
User NL Query
      |
      v
FastAPI /query endpoint
      |
      v
[Context Loading]
  Layer 1: Schema (auto-introspect at start)
  Layer 2: Domain KB (load from kb/domain/)
  Layer 3: Memory (load from agent/memory/)
      |
      v
[Query Planning] -- GPT-4o via OpenRouter
      |
      v
[Multi-DB Execution] -- MCP Toolbox
  PostgreSQL | SQLite | MongoDB | DuckDB
      |
      v
[Self-Correction Loop]
  Error detected? --> Diagnose --> Retry (max 3)
      |
      v
[Result Validation] -- Data contract check
      |
      v
[Response] {answer, query_trace, confidence}
      |
      v
[Corrections Log] -- Append failure/fix to kb/corrections/
```

---

## Definition of Done (Interim — April 15)

1. FastAPI server starts with `uvicorn agent.main:app` and responds to `GET /health`
2. Agent answers a natural language question against the Yelp PostgreSQL dataset correctly
3. Agent answers a natural language question against SQLite and at least one other DB type
4. KB v1 (architecture) and KB v2 (domain/Yelp) have ≥1 injection-tested document each
5. Evaluation harness runs against ≥5 DAB queries and produces a score log with query trace
6. `planning/inception.md` exists with team approval record (date + hardest question answered)
7. `utils/` has ≥3 documented, tested utility modules
8. README.md contains setup instructions reproducible from a clean clone

## Definition of Done (Final — April 18)

9. Agent handles all 4 DB types with self-correction on execution failure
10. KB v3 (corrections log) has ≥3 entries that demonstrably change agent behaviour
11. `probes/probes.md` has ≥15 adversarial probes across ≥3 failure categories
12. DAB benchmark run: 54 queries × 50 trials, results JSON submitted via GitHub PR
13. Score log shows measurable improvement between first run and final submission
14. Signal Corps: ≥2 X threads/week, ≥1 article per member (600+ words), community log
15. Demo video (≤8 min) hosted publicly, shows self-correction + context layers + harness
