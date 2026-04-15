# OracleForge Data Agent — Requirements

## Intent Analysis Summary
- **User Request**: Build a production-grade, multi-database analytics agent evaluated against the DataAgentBench (DAB) benchmark
- **Request Type**: New Project (Greenfield)
- **Scope Estimate**: System-wide — 20+ source modules, 4 DB types (3 via Google MCP Toolbox, 1 via custom DuckDB bridge), eval harness, KB system, test suite
- **Complexity Estimate**: Complex — multi-layer architecture, heterogeneous MCP backends, self-correction loop, benchmark integration

---

## Functional Requirements

### FR-01: Agent Facade
- `run_agent(question: str, db_hints: list[str]) -> AgentResult` is the single public entry point
- `AgentResult` dataclass: `{ answer: str, confidence: float, trace_id: str, tool_calls: list, failure_count: int }`
- Defined in `agent/data_agent/types.py` (shared across all modules)

### FR-02: 6-Layer Context Pipeline
Each query MUST compose all 6 layers in this precedence order (highest → lowest):
- Layer 6: Latest user question
- Layer 5: Interaction memory (runtime memory + kb/corrections)
- Layer 4: Runtime context (session_id, discovered tools, selected DBs, route proposals, mode flags)
- Layer 3: Institutional knowledge (kb/architecture + kb/evaluation + AGENT.md)
- Layer 2: Human annotations (query-aware retrieval from kb/domain)
- Layer 1: Table usage (DB inventory, schema summary, join-key hints)
- Backward-compat aliases: `schema_and_metadata → table_usage`, `institutional_and_domain → human_annotations + institutional_knowledge`

### FR-03: Multi-Database Tool Routing

All upstream agent components (ToolRegistry, conductor, planner, synthesizer) interact with a **single unified `MCPClient`** interface. All 4 databases appear as tool entries in one flat registry. No upstream component knows or cares which physical backend served a given tool.

**`tools.yaml` — Single MCP Configuration for All 4 DB Types**:

`tools.yaml` is the authoritative MCP configuration for the entire project. It declares tools for all four databases. The DuckDB tool entry uses `type: duckdb_bridge` and an `endpoint` pointing to the custom bridge server — it does NOT imply that Google MCP Toolbox manages DuckDB:

```yaml
# tools.yaml — OracleForge MCP tool configuration (all 4 DB types)
sources:
  postgres_db:
    kind: postgres
    connection: ${POSTGRES_URL}
  mongo_db:
    kind: mongodb
    connection: ${MONGODB_URL}
    database: ${MONGODB_DB}
  sqlite_db:
    kind: sqlite
    path: ${SQLITE_PATH}
  duckdb_bridge:
    kind: duckdb_bridge          # custom — NOT a Google MCP Toolbox kind
    endpoint: ${DUCKDB_BRIDGE_URL}
    path: ${DUCKDB_PATH}
    read_only: true
    timeout_seconds: ${DUCKDB_BRIDGE_TIMEOUT_SECONDS}

tools:
  query_postgresql:
    kind: postgres-sql
    source: postgres_db
    description: "Execute read-only SQL against PostgreSQL"
  query_mongodb:
    kind: mongodb-aggregate
    source: mongo_db
    description: "Execute aggregation pipeline against MongoDB"
  query_sqlite:
    kind: sqlite-sql
    source: sqlite_db
    description: "Execute read-only SQL against SQLite"
  query_duckdb:
    kind: duckdb_bridge_sql       # custom kind; handled by DuckDBBridgeClient
    source: duckdb_bridge
    description: "Execute read-only SQL against DuckDB via custom MCP bridge"
```

This means: when challenge reviewers examine `tools.yaml`, they see a 4-DB MCP configuration. Google MCP Toolbox handles the first 3 tools; the DuckDB entry is declared in the same config file but is backed by the custom bridge.

**Unified Interface** (`agent/data_agent/mcp_toolbox_client.py`):
- `MCPClient` reads `tools.yaml` at init to build its authoritative 4-tool registry
- Exposes one public class `MCPClient` with two methods: `discover_tools() → list[ToolDescriptor]` and `invoke_tool(tool_name, params) → InvokeResult`
- `discover_tools()` returns the full 4-tool list from the registry (loaded from `tools.yaml`); no backend is queried just to discover tools
- `invoke_tool()` inspects the tool's `kind` field: standard kinds (`postgres-sql`, `mongodb-aggregate`, `sqlite-sql`) → dispatch to Google MCP Toolbox at `MCP_TOOLBOX_URL`; `duckdb_bridge_sql` → dispatch to `DuckDBBridgeClient` — this routing is invisible to callers
- When `AGENT_OFFLINE_MODE=1` or `AGENT_USE_MCP=0`: returns a merged stub tool list + stub results covering all 4 DB types; no HTTP calls made

**Internal Provider A — Google MCP Toolbox**:
- Handles `postgres-sql`, `mongodb-aggregate`, `sqlite-sql` tool invocations via `MCP_TOOLBOX_URL`
- Managed entirely inside `mcp_toolbox_client.py`; not exposed as a public class

**Internal Provider B — Custom DuckDB MCP Bridge** (`agent/data_agent/duckdb_bridge_client.py`):
- Handles `duckdb_bridge_sql` tool invocations via `DUCKDB_BRIDGE_URL`
- Encapsulated in `duckdb_bridge_client.py`; imported **only** by `MCPClient` inside `mcp_toolbox_client.py`
- Never imported directly by any other module — it is a private implementation detail of `MCPClient`

**Dispatch rule** (internal to `MCPClient`, invisible upstream):
- `kind` in `{postgres-sql, mongodb-aggregate, sqlite-sql}` → Google MCP Toolbox
- `kind == duckdb_bridge_sql` → `DuckDBBridgeClient`
- `ToolRegistry` and all upstream code see one flat list of 4 tools, sourced from `tools.yaml`

### FR-03b: DuckDB MCP Bridge Contract (Internal to MCPClient)
The custom DuckDB bridge is an implementation detail of `DuckDBBridgeClient` inside `duckdb_bridge_client.py`. The contract below is the bridge server's wire protocol — only `DuckDBBridgeClient` speaks it. No other module references `DUCKDB_BRIDGE_URL` or sends requests to the bridge directly.

The custom DuckDB bridge exposes the following interface:

**Schema Discovery**:
- Endpoint: `GET {DUCKDB_BRIDGE_URL}/tools` (or MCP-compatible `/list_tools`)
- Returns: list of tool descriptors with `name`, `description`, `parameters` fields
- Must include a `schema_summary` field per tool describing available tables and column types
- Timeout: `DUCKDB_BRIDGE_TIMEOUT_SECONDS` (default: same as `MCP_TIMEOUT_SECONDS=8`)

**Query Execution**:
- Endpoint: `POST {DUCKDB_BRIDGE_URL}/invoke`
- Request body: `{ "tool": "<tool_name>", "parameters": { "sql": "<SELECT ...>" } }`
- Response: `{ "success": bool, "result": <rows>, "error": "<message if failed>" }`
- Only SELECT statements are accepted — the bridge MUST reject INSERT/UPDATE/DELETE/DROP/CREATE with a structured error
- File path is fixed to `DUCKDB_PATH` (env var) — the bridge enforces this server-side

**Error Behavior**:
- Query syntax errors: `{ "success": false, "error": "query_error: <message>", "error_type": "query" }`
- Mutation attempt: `{ "success": false, "error": "read_only_violation: only SELECT is permitted", "error_type": "policy" }`
- File not found: `{ "success": false, "error": "duckdb_path_not_found: <path>", "error_type": "config" }`
- Timeout: `requests.Timeout` raised after `DUCKDB_BRIDGE_TIMEOUT_SECONDS`; treated as `db-type` failure category
- All error responses include `"error_type"` used by `failure_diagnostics.classify()`

**Read-Only Enforcement**:
- Bridge server enforces read-only; `ToolPolicy` also blocks mutation keywords as a defense-in-depth layer
- `DUCKDB_PATH` is the only accessible file; bridge rejects any path traversal in query parameters

### FR-04: Self-Correction Loop (max 3 retries)
1. Execute MCP tool call (either Google MCP Toolbox or DuckDB bridge)
2. On failure → `failure_diagnostics.classify(error, context)` → 4 categories: `query`, `join-key`, `db-type`, `data-quality`
3. `execution_planner.propose_correction(diagnosis, context_layers)`
4. Write structured correction entry to `kb/corrections/corrections_log.md`
5. Retry with corrected plan (capped at `AGENT_SELF_CORRECTION_RETRIES`, default 3)
6. Emit trace event for every step including retries

DuckDB bridge `error_type` field maps directly to failure categories:
- `"query"` → `query` category
- `"policy"` → `db-type` category (wrong tool for mutation)
- `"config"` → `db-type` category (misconfigured path)

### FR-05: Persistent Memory (3-layer)
- `index.json`: topic → file mapping
- `topics/<key>.md`: condensed topic knowledge (max `AGENT_MEMORY_TOPIC_CHARS=2500` chars)
- `sessions/<session_id>.jsonl`: turn-by-turn transcript (max `AGENT_MEMORY_SESSION_ITEMS=12` items)
- Memory is lazy-initialized on first write (zero side effects on import)

### FR-06: Append-Only Event Ledger
Every tool call emits a structured JSONL event to `AGENT_RUNTIME_EVENTS_PATH`:
```json
{
  "event_type": "...", "session_id": "...", "timestamp": "...",
  "tool_name": "...", "db_type": "...", "input_summary": "...",
  "outcome": "...", "diagnosis": "...", "retry_count": 0
}
```
Events from DuckDB bridge calls include `"backend": "duckdb_bridge"` to distinguish from Google MCP Toolbox calls.

### FR-07: DAB Evaluation Harness
- `eval/run_dab_benchmark.py`: 12 datasets, up to 54 queries, 5 trials/query default
- `eval/run_trials.py`: local trial runner, default datasets: `bookreview` + `stockmarket`
- `eval/score_results.py`: pass@1 scorer; outputs `dab_detailed.json` + `dab_submission.json`
- In offline mode: run with stub/mock LLM responses — full pipeline exercised, no API or bridge calls
- pass@1 = (pass count / total trials) per query

### FR-08: AGENT.md Loaded First at Every Session
- `agent/AGENT.md` is loaded first into Layer 3 (institutional knowledge) at every session start
- Traced via `agent_context_loaded` event

### FR-09: Knowledge Base
- 4 subdirectories: `kb/architecture/`, `kb/domain/`, `kb/evaluation/`, `kb/corrections/`
- Full seed: 2-3 substantive `.md` documents per subdir at build time
- `corrections_log.md` seeded with 3 real DAB examples (PostgreSQL aggregation, MongoDB field access, DuckDB LATERAL JOIN)
- Retrieval: keyword extraction → document overlap scoring → filename stem overlap → freshness bonus

### FR-10: Sandbox Execution Path
- `sandbox/sandbox_server.py`: HTTP server with `/execute` and `/health` endpoints
- `agent/data_agent/sandbox_client.py`: client that routes Python code execution to sandbox
- Activated when `AGENT_USE_SANDBOX=1`; coexists with MCP path
- `SANDBOX_ALLOWED_ROOTS` enforced server-side; `SANDBOX_PY_TIMEOUT_SECONDS=3`

### FR-11: Adversarial Probes
- `probes/probes.md`: 15+ probes across 3 categories: schema confusion, cross-DB join traps, correction memory gaming
- Each probe: input → expected behavior → what it tests → fix evidence

### FR-12: Shared Types Module
- `agent/data_agent/types.py` with all shared dataclasses/TypedDicts
- Key types: `AgentResult`, `TraceEvent`, `ContextPacket`, `ExecutionStep`, `CorrectionEntry`

### FR-13: LLM Backend Configuration
- LLM provider: OpenRouter API (`OPENROUTER_BASE_URL`)
- Model: configurable via `OPENROUTER_MODEL` env var — default is a Gemini model (e.g. `google/gemini-2.0-flash-001`); any OpenRouter-compatible model ID is valid
- No model name hardcoded in source — always read from `config.py` which reads from env
- `OPENROUTER_API_KEY` required when `AGENT_OFFLINE_MODE=0`
- `AGENT_MAX_TOKENS`, `AGENT_TEMPERATURE` also configurable via env

---

## Non-Functional Requirements

### NFR-01: Offline Mode
- `AGENT_OFFLINE_MODE=1` MUST work without any API calls — no OpenRouter, no Google MCP Toolbox, no DuckDB bridge
- Stub LLM responses are deterministic; full pipeline (context layering, memory, events) is exercised
- Google MCP Toolbox stub returns hardcoded tool list + query results from `config.py`
- DuckDB bridge stub returns hardcoded schema + SELECT results from `config.py` (separate stub set, keyed by `"duckdb"`)
- Both stubs are toggled by the same `AGENT_OFFLINE_MODE` flag — no separate flag needed

### NFR-02: Timeout Guards
- All Google MCP Toolbox calls ≤ `AGENT_TIMEOUT_SECONDS` (default 45s) at conductor level
- DuckDB bridge calls ≤ `DUCKDB_BRIDGE_TIMEOUT_SECONDS` (default: same as `MCP_TIMEOUT_SECONDS=8`)
- Sandbox Python execution ≤ `SANDBOX_PY_TIMEOUT_SECONDS` (default 3s)
- Google MCP Toolbox discovery/invoke ≤ `MCP_TIMEOUT_SECONDS` (default 8s)

### NFR-03: Retry Cap
- `AGENT_SELF_CORRECTION_RETRIES` (default 3, configurable via .env) — applies to both backends
- `AGENT_MAX_EXECUTION_STEPS=6`

### NFR-04: No Secrets in Code
- All credentials from `.env` file only
- No hardcoded API keys, DB passwords, model names, or bridge URLs in source code

### NFR-05: Test Suite
- All tests pass: `python3 -m unittest discover -s tests -v`
- Smoke test: single DAB query, 2 trials, output to `results/`

### NFR-06: Performance
- `AGENT_MAX_TOKENS=700`, `AGENT_TEMPERATURE=0.1`
- Session memory capped at `AGENT_MEMORY_SESSION_ITEMS=12` turns
- Topic memory capped at `AGENT_MEMORY_TOPIC_CHARS=2500` chars

### NFR-07: Python Version
- Python 3.11+ required

---

## Security Requirements (SECURITY Extension — Enforced)

### SEC-03: Structured Logging
- All components use Python `logging` framework (not print statements)
- Logs include: timestamp, correlation ID (session_id), log level, message
- No secrets, API keys, DB connection strings, or DuckDB file paths in log output
- DuckDB bridge requests/responses logged at DEBUG level only; SQL queries redacted at INFO+

### SEC-05: Input Validation
- `run_agent()` validates `question` (type str, max 4096 chars) and `db_hints` (list of str, max 10 items)
- `ToolPolicy` validates tool payloads: size cap, SQL mutation keyword blocking (INSERT/UPDATE/DELETE/DROP/CREATE/ALTER)
- DuckDB bridge client validates that only `db_type == "duckdb"` requests are routed to the bridge; any other routing is a hard error
- DuckDB bridge `sql` parameter must not exceed `SANDBOX_MAX_PAYLOAD_CHARS` before sending to bridge
- No raw user input concatenated into DB queries — parameterized or bridge-enforced only

### SEC-09: Security Hardening
- Generic error messages returned to callers (no stack traces, bridge URLs, or file paths exposed externally)
- Correction log entries sanitized before writing (SQL stripped to summary)
- No default credentials in config files; `DUCKDB_BRIDGE_URL` has no default that points to a live server

### SEC-10: Supply Chain
- `requirements.txt` uses pinned exact versions
- All dependencies from PyPI (official registry only)

### SEC-11: Secure Design
- Security-critical logic (input validation, payload size limits, SQL mutation blocking) isolated in `agent/runtime/tooling.py` (`ToolPolicy`)
- DuckDB bridge read-only enforcement is a bridge-server responsibility; `ToolPolicy` adds a defense-in-depth client-side check
- Sandbox allowed roots enforced server-side

### SEC-13: Deserialization Safety
- All JSONL parsing uses `json.loads()` with try/except; no `pickle` or `eval` on untrusted data
- DuckDB bridge response parsing uses `json.loads()` with schema validation before use
- Event ledger entries validated before append

### SEC-15: Exception Handling
- All external calls (Google MCP Toolbox HTTP, DuckDB bridge HTTP, OpenRouter API, file I/O) have explicit try/except with safe fallbacks
- DuckDB bridge `requests.Timeout` → caught, mapped to `db-type` failure category, correction loop triggered
- DuckDB bridge connection refused → caught, mapped to `db-type` failure category
- Resource cleanup in error paths (file handles closed, connections released)
- Global error handler in conductor catches unhandled exceptions and returns safe `AgentResult`

---

## Property-Based Testing Requirements (PBT Extension — Partial: PBT-02/03/07/08/09)

### PBT-02: Round-Trip Properties
- Context packet serialization/deserialization round-trip test
- Event JSONL serialize/deserialize round-trip test (including `backend` field)
- Memory topic write/read round-trip test

### PBT-03: Invariant Properties
- Failure classification always returns one of 4 valid categories (`query`, `join-key`, `db-type`, `data-quality`)
- Context layer precedence invariant: Layer 6 always overrides Layer 1
- Score computation: pass@1 always in [0.0, 1.0]
- DuckDB dispatch invariant: within `MCPClient`, any tool sourced from the DuckDB bridge is always dispatched to `DuckDBBridgeClient`; Google MCP Toolbox tools are never sent to the bridge

### PBT-07/08/09: Framework Selection
- Framework: **Hypothesis** (Python, mature, excellent shrinking)
- Add `hypothesis` to `requirements.txt`
- PBT tests in `tests/test_properties.py` (separate from example-based tests)
- Seeds logged on failure; CI logs random seed per run

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| LLM Backend | OpenRouter API | Model configurable via `OPENROUTER_MODEL` env var; default `google/gemini-2.0-flash-001` |
| MCP Config | `tools.yaml` | Single MCP configuration declaring all 4 DB tools; read by `MCPClient` at init |
| DB Backend (3 DBs) | Google MCP Toolbox | Handles `postgres-sql`, `mongodb-aggregate`, `sqlite-sql` kinds via `MCP_TOOLBOX_URL` |
| DB Backend (DuckDB) | Custom DuckDB MCP Bridge | Handles `duckdb_bridge_sql` kind via `DUCKDB_BRIDGE_URL`; read-only; path-restricted |
| Memory | File-based | `.oracle_forge_memory/` directory |
| Evaluation | DataAgentBench | `external/DataAgentBench` scaffold |
| Config | `.env` file | All secrets and model names from env |
| HTTP client | `requests` | Used for both MCP Toolbox and DuckDB bridge |
| PBT Framework | Hypothesis | PBT-02/03/07/08/09 only |

---

## Environment Variables (Key Additions / Changes)

| Variable | Description | Default |
|---|---|---|
| `OPENROUTER_MODEL` | OpenRouter model ID (any Gemini or other model) | `google/gemini-2.0-flash-001` |
| `MCP_TOOLBOX_URL` | URL of the Google MCP Toolbox server (PostgreSQL/MongoDB/SQLite) | `http://localhost:5000` |
| `DUCKDB_BRIDGE_URL` | URL of the custom DuckDB MCP bridge server | `http://localhost:5001` |
| `DUCKDB_BRIDGE_TIMEOUT_SECONDS` | Per-request timeout for DuckDB bridge calls | `8` (same as `MCP_TIMEOUT_SECONDS`) |
| `DUCKDB_PATH` | Absolute path to the DuckDB file (enforced by bridge; declared in `tools.yaml`) | `./data/duckdb/main.duckdb` |
| `TOOLS_YAML_PATH` | Path to `tools.yaml`; read by `MCPClient` at init to build 4-DB tool registry | `./tools.yaml` |

---

## Directory Structure (Confirmed)

```
OracleForge/
├── agent/
│   ├── AGENT.md
│   ├── runtime/
│   │   ├── conductor.py
│   │   ├── tooling.py
│   │   ├── memory.py
│   │   └── events.py
│   └── data_agent/
│       ├── types.py                    # ADDED (Q2=A)
│       ├── oracle_forge_agent.py
│       ├── execution_planner.py
│       ├── mcp_toolbox_client.py       # handles Google MCP Toolbox + DuckDB bridge routing
│       ├── result_synthesizer.py
│       ├── context_layering.py
│       ├── failure_diagnostics.py
│       ├── knowledge_base.py
│       ├── sandbox_client.py           # ADDED (Q1=A)
│       └── config.py
├── sandbox/
│   └── sandbox_server.py              # ADDED (Q1=A)
├── kb/
│   ├── architecture/                  # Full seed (Q6=A)
│   ├── domain/
│   ├── evaluation/
│   └── corrections/corrections_log.md
├── eval/
│   ├── run_dab_benchmark.py
│   ├── run_trials.py
│   └── score_results.py
├── utils/
│   ├── db_utils.py
│   ├── text_utils.py
│   └── trace_utils.py
├── tests/
│   ├── test_conductor.py
│   ├── test_context_layering.py
│   ├── test_failure_diagnostics.py
│   ├── test_memory.py
│   └── test_properties.py             # ADDED (PBT-09)
├── probes/probes.md
├── tools.yaml                         # MCP config: all 4 DB types; DuckDB entry uses kind: duckdb_bridge
├── requirements.txt
├── .env.example
└── README.md
```

---

## Decisions from Clarification Questions

| Q | Decision | Impact |
|---|---|---|
| Q1 | Include sandbox execution path | Add `sandbox/sandbox_server.py`, `agent/data_agent/sandbox_client.py` |
| Q2 | Create `types.py` | Shared dataclasses across all modules |
| Q3 | Offline = full stub pipeline | Deterministic stub LLM + separate stubs for toolbox and DuckDB bridge |
| Q4 | Smoke datasets: bookreview + stockmarket | Default in `run_trials.py` |
| Q5 | MCP offline = hardcoded stub tool list | Separate stubs for toolbox (3 DBs) and DuckDB bridge in `config.py` |
| Q6 | Full KB seed | 2-3 docs per kb/ subdir |
| Q7 | Skip User Stories | Direct to Workflow Planning |
| Q8 | Security extension ENABLED | SECURITY rules are blocking constraints |
| Q9 | PBT Partial | PBT-02/03/07/08/09 enforced; add `hypothesis` to deps |
| Q10 | Skip Application Design | Proceed to Units Generation then Code Generation |

## Post-Approval Revisions

| Change | Requested By | Applied |
|---|---|---|
| LLM model configurable via `OPENROUTER_MODEL`; default Gemini | User | FR-13, Tech Stack, NFR-04 |
| DuckDB uses custom MCP bridge, not Google MCP Toolbox | User | FR-03, FR-03b, Tech Stack, NFR-01, NFR-02, SEC-03/05/09/13/15 |
| `tools.yaml` scoped to 3 DBs only (PostgreSQL, MongoDB, SQLite) | User | FR-03, Directory Structure |
| DuckDB bridge contract: schema discovery, query exec, error types, read-only, path restriction | User | FR-03b (new section) |
| Event ledger: `backend` field distinguishes bridge from toolbox calls | User | FR-06 |
| PBT-03 invariant: DuckDB routing always goes to bridge | User | PBT-03 |
