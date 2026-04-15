# Units of Work — OracleForge Data Agent

## Decomposition Strategy
Single-service monorepo with 5 logically-ordered development units. Units are ordered by dependency: each unit can only be started once all units it depends on are complete. The architecture was pre-specified in the project requirements, so decomposition follows the natural layering described there.

---

## Unit U1 — Foundation

**Purpose**: Zero-dependency base layer. All other units import from this one.

**Modules**:
| File | Responsibility |
|---|---|
| `agent/data_agent/types.py` | All shared dataclasses: `AgentResult`, `TraceEvent`, `ContextPacket`, `ExecutionStep`, `CorrectionEntry` |
| `agent/data_agent/config.py` | Env-driven feature flags; offline stubs for MCP and DuckDB bridge |
| `agent/runtime/events.py` | Append-only JSONL event ledger; `emit_event()` |
| `utils/text_utils.py` | Keyword extraction, document overlap scoring, freshness bonus |
| `utils/trace_utils.py` | Structured event builders for trace events |
| `utils/db_utils.py` | Connection helper stubs for all 4 DB types |

**Entry Points**: `config.py` (imported by all modules), `types.py` (imported by all modules)

**Acceptance Criteria**:
- All dataclasses importable with zero side effects
- `AGENT_OFFLINE_MODE=1` toggles stub responses without any network calls
- `emit_event()` appends JSONL line to configured path; safe to call before file exists
- `python3 -m unittest tests/test_properties.py` — round-trip PBT for event serialization passes

---

## Unit U2 — Data Layer

**Purpose**: Knowledge retrieval, context construction, unified DB tool interface, and failure diagnosis. No orchestration logic — pure data transformation and retrieval.

**Modules**:
| File | Visibility | Responsibility |
|---|---|---|
| `agent/data_agent/knowledge_base.py` | Public | Load kb/ subdirs; keyword retrieval; freshness-weighted ranking |
| `agent/data_agent/context_layering.py` | Public | 6-layer context packet; precedence composition; backward-compat aliases |
| `agent/data_agent/failure_diagnostics.py` | Public | 4-category failure classifier (`query`/`join-key`/`db-type`/`data-quality`) |
| `agent/data_agent/mcp_toolbox_client.py` | **Public facade** | `MCPClient` — reads `tools.yaml` at init to build 4-DB tool registry; `discover_tools()` returns all 4 tools; `invoke_tool()` dispatches by `kind` field — invisible to callers |
| `agent/data_agent/duckdb_bridge_client.py` | **Private impl** | `DuckDBBridgeClient` — speaks the DuckDB bridge wire protocol (`kind: duckdb_bridge_sql`); imported **only** by `mcp_toolbox_client.py`; never imported elsewhere |

**Unified DB Client Design**:

```
tools.yaml  <-- single MCP config; all 4 DB tools declared here
  (postgres-sql / mongodb-aggregate / sqlite-sql / duckdb_bridge_sql)
        |
        | loaded at init
        v
Upstream (ToolRegistry, conductor, planner, synthesizer)
         |
         | imports MCPClient only; sees 4-tool flat list
         v
  mcp_toolbox_client.py   <-- single public entry point
  +--------------------------------------------+
  | MCPClient                                  |
  |  discover_tools()  <-- returns 4 tools     |
  |  invoke_tool(name) --> dispatch by kind:   |
  |    postgres/mongo/sqlite  --> MCP Toolbox  |
  |    duckdb_bridge_sql      --> private below|
  +--------------------------------------------+
         |  internal import only
         v
  duckdb_bridge_client.py
  +-----------------------+
  | DuckDBBridgeClient    |
  |  invoke(sql)          |
  +-----------------------+
         |
         v
  Custom DuckDB MCP Bridge (DUCKDB_BRIDGE_URL)
```

**Depends On**: U1 (`types.py`, `config.py`, `text_utils.py`)

**Acceptance Criteria**:
- `build_context_packet()` composes all 6 layers; Layer 6 overrides Layer 1
- `failure_diagnostics.classify()` always returns one of the 4 valid categories (PBT-03 invariant)
- `MCPClient` loads `tools.yaml` at init; `discover_tools()` returns all 4 DB tools from the registry without querying any live backend
- `MCPClient.invoke_tool()` dispatches internally by `kind`; callers never reference `DuckDBBridgeClient` directly
- `duckdb_bridge_client.py` has zero imports from outside U2 (self-contained DuckDB protocol)
- Offline stubs in `config.py` provide the same 4-tool flat list from `tools.yaml` format; no HTTP calls made
- `tools.yaml` satisfies challenge requirement: single MCP config file covering all 4 DB types
- `python3 -m unittest tests/test_context_layering.py tests/test_failure_diagnostics.py` passes

---

## Unit U3 — Runtime Layer

**Purpose**: Persistent memory, tool policy enforcement, and the orchestration spine (conductor).

**Modules**:
| File | Responsibility |
|---|---|
| `agent/runtime/memory.py` | 3-layer file-based memory (index/topics/sessions); lazy init |
| `agent/runtime/tooling.py` | `ToolRegistry` (db-type hint → tool); `ToolPolicy` (mutation guard, size cap) |
| `agent/runtime/conductor.py` | Session lifecycle; 6-layer context assembly; self-correction loop; event emission |

**Depends On**: U1 (all), U2 (all)

**Acceptance Criteria**:
- Memory module importable with zero side effects before first write
- `ToolPolicy` blocks INSERT/UPDATE/DELETE/DROP/CREATE/ALTER queries
- Conductor executes self-correction loop up to `AGENT_SELF_CORRECTION_RETRIES` retries
- Every retry emits a trace event with `retry_count` field
- `python3 -m unittest tests/test_conductor.py tests/test_memory.py` passes

---

## Unit U4 — Agent + Sandbox

**Purpose**: Planning, answer synthesis, agent facade, and sandbox execution path.

**Modules**:
| File | Responsibility |
|---|---|
| `agent/data_agent/execution_planner.py` | Multi-step plan builder; correction proposal generator |
| `agent/data_agent/result_synthesizer.py` | Grounded answer from execution evidence + context |
| `agent/data_agent/oracle_forge_agent.py` | Single public facade: `run_agent(question, db_hints) → AgentResult` |
| `agent/data_agent/sandbox_client.py` | HTTP client for `/execute` + `/health` on sandbox server |
| `sandbox/sandbox_server.py` | Flask HTTP server: `/execute` + `/health`; `SANDBOX_ALLOWED_ROOTS` enforced |
| `agent/AGENT.md` | Agent identity, behavioral constraints, operating instructions |

**Depends On**: U1, U2, U3

**Acceptance Criteria**:
- `run_agent()` returns `AgentResult` with all fields populated
- `AGENT_OFFLINE_MODE=1` exercises full pipeline with stub responses (no API, no MCP, no bridge)
- Sandbox server rejects paths outside `SANDBOX_ALLOWED_ROOTS`
- Sandbox client health-checks server before sending payloads
- `oracle_forge_agent.py` loads `AGENT.md` into Layer 3 at session start

---

## Unit U5 — Eval + Supporting Files

**Purpose**: Benchmark harness, KB seed content, configuration files, documentation, and adversarial probes.

**Modules / Files**:
| File | Responsibility |
|---|---|
| `eval/run_dab_benchmark.py` | DAB driver; 12 datasets; pass@1 scoring; JSON output |
| `eval/run_trials.py` | Local trial runner; default bookreview + stockmarket |
| `eval/score_results.py` | pass@1 scorer from results JSON |
| `kb/architecture/*.md` | 2-3 seed docs: Claude Code architecture, tool scoping, 6-layer context |
| `kb/domain/*.md` | 2-3 seed docs: DAB schema, query patterns, join-key glossary |
| `kb/evaluation/*.md` | 2-3 seed docs: DAB format, scoring, harness schema, 4 failure categories |
| `kb/corrections/corrections_log.md` | 3 seeded examples: PostgreSQL aggregation, MongoDB field, DuckDB LATERAL |
| `tools.yaml` | MCP config for all 4 DB types: PostgreSQL (`postgres-sql`), MongoDB (`mongodb-aggregate`), SQLite (`sqlite-sql`), DuckDB (`duckdb_bridge_sql`); DuckDB entry points to custom bridge via `DUCKDB_BRIDGE_URL` |
| `requirements.txt` | Pinned exact versions; includes `hypothesis` |
| `.env.example` | Updated: `OPENROUTER_MODEL=google/gemini-2.0-flash-001`, `DUCKDB_BRIDGE_URL` |
| `probes/probes.md` | 15+ adversarial probes across 3 categories |
| `README.md` | Architecture diagram + setup + server links |
| `tests/test_properties.py` | Hypothesis PBT: round-trip + invariant tests (PBT-02/03) |

**Depends On**: U1–U4

**Acceptance Criteria**:
- `python3 eval/run_trials.py --trials 2 --output results/smoke.json` completes without error
- `python3 eval/score_results.py --results results/smoke.json` outputs valid JSON with pass@1 in [0.0, 1.0]
- `python3 -m unittest discover -s tests -v` — all tests pass including PBT
- KB retrieval returns relevant docs for sample DAB query keywords
