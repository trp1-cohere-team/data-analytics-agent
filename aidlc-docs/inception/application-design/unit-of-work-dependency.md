# Unit of Work Dependency Matrix

## Dependency Graph

```
U1 Foundation
  |
  +---> U2 Data Layer
  |       |
  |       +---> U3 Runtime Layer
  |               |
  +---------------+---> U4 Agent + Sandbox
                          |
                          +---> U5 Eval + Supporting Files
```

## Dependency Matrix

| | U1 Foundation | U2 Data Layer | U3 Runtime Layer | U4 Agent + Sandbox | U5 Eval + Supporting |
|---|---|---|---|---|---|
| **U1 Foundation** | — | — | — | — | — |
| **U2 Data Layer** | REQUIRES | — | — | — | — |
| **U3 Runtime Layer** | REQUIRES | REQUIRES | — | — | — |
| **U4 Agent + Sandbox** | REQUIRES | REQUIRES | REQUIRES | — | — |
| **U5 Eval + Supporting** | REQUIRES | REQUIRES | REQUIRES | REQUIRES | — |

---

## Inter-Unit Import Map

### U2 Internal (private — not visible outside U2)

| Importing File | Imports From | Specific Symbols | Notes |
|---|---|---|---|
| `U2 mcp_toolbox_client.py` | `U2 duckdb_bridge_client.py` | `DuckDBBridgeClient` | **Private intra-U2 import only**; never re-exported |

### U2 from U1

| Importing File | Imports From | Specific Symbols |
|---|---|---|
| `U2 knowledge_base.py` | `U1 config.py` | `KB_ROOT`, `AGENT_CONTEXT_PATH` |
| `U2 knowledge_base.py` | `U1 text_utils.py` | `extract_keywords`, `score_overlap` |
| `U2 context_layering.py` | `U1 types.py` | `ContextPacket`, `LayerContent` |
| `U2 context_layering.py` | `U1 config.py` | `AGENT_OFFLINE_MODE` |
| `U2 failure_diagnostics.py` | `U1 types.py` | `FailureDiagnosis` |
| `U2 mcp_toolbox_client.py` | `U1 config.py` | `MCP_TOOLBOX_URL`, `MCP_TIMEOUT_SECONDS`, `TOOLS_YAML_PATH`, `AGENT_OFFLINE_MODE`, offline stub tool list |
| `U2 mcp_toolbox_client.py` | `U1 types.py` | `ToolDescriptor`, `InvokeResult` |
| `U2 duckdb_bridge_client.py` | `U1 config.py` | `DUCKDB_BRIDGE_URL`, `DUCKDB_BRIDGE_TIMEOUT_SECONDS`, DuckDB offline stubs |
| `U2 duckdb_bridge_client.py` | `U1 types.py` | `InvokeResult` |

### U3 from U1 and U2

> **Rule**: U3 modules import `MCPClient` from `mcp_toolbox_client.py` only. No U3 module imports `DuckDBBridgeClient` or `duckdb_bridge_client.py`.

| Importing File | Imports From | Specific Symbols |
|---|---|---|
| `U3 memory.py` | `U1 config.py` | `AGENT_MEMORY_ROOT`, `AGENT_MEMORY_SESSION_ITEMS` |
| `U3 memory.py` | `U1 types.py` | `MemoryTurn` |
| `U3 tooling.py` | `U1 types.py` | `ToolDescriptor` |
| `U3 tooling.py` | `U2 mcp_toolbox_client.py` | `MCPClient` |
| `U3 conductor.py` | `U1 types.py` | `AgentResult`, `TraceEvent` |
| `U3 conductor.py` | `U1 events.py` | `emit_event` |
| `U3 conductor.py` | `U1 config.py` | all runtime flags |
| `U3 conductor.py` | `U2 context_layering.py` | `build_context_packet` |
| `U3 conductor.py` | `U2 knowledge_base.py` | `load_layered_kb_context` |
| `U3 conductor.py` | `U2 failure_diagnostics.py` | `classify` |
| `U3 conductor.py` | `U2 mcp_toolbox_client.py` | `MCPClient` |
| `U3 conductor.py` | `U3 memory.py` | `MemoryManager` |
| `U3 conductor.py` | `U3 tooling.py` | `ToolRegistry`, `ToolPolicy` |

### U4 from U1–U3

> **Rule**: No U4 module imports `DuckDBBridgeClient` or `duckdb_bridge_client.py`.

| Importing File | Imports From | Specific Symbols |
|---|---|---|
| `U4 execution_planner.py` | `U1 types.py` | `ExecutionStep`, `ContextPacket` |
| `U4 execution_planner.py` | `U1 config.py` | `OPENROUTER_*` flags |
| `U4 result_synthesizer.py` | `U1 types.py` | `AgentResult`, `ContextPacket` |
| `U4 result_synthesizer.py` | `U1 config.py` | `OPENROUTER_*` flags |
| `U4 oracle_forge_agent.py` | `U3 conductor.py` | `OracleForgeConductor` |
| `U4 oracle_forge_agent.py` | `U1 config.py` | `AGENT_CONTEXT_PATH`, `AGENT_SESSION_ID` |
| `U4 sandbox_client.py` | `U1 config.py` | `SANDBOX_URL`, `SANDBOX_TIMEOUT_SECONDS` |

### U5 from U1–U4

| Importing File | Imports From | Specific Symbols |
|---|---|---|
| `U5 run_dab_benchmark.py` | `U4 oracle_forge_agent.py` | `OracleForgeAgent` |
| `U5 run_trials.py` | `U4 oracle_forge_agent.py` | `OracleForgeAgent` |
| `U5 score_results.py` | — (standalone) | reads JSON files only |

---

## Visibility Contract Summary

| Module | Public API Exported | May Be Imported By |
|---|---|---|
| `mcp_toolbox_client.py` | `MCPClient` | U3, U4 (via U3), U5 (tests) |
| `duckdb_bridge_client.py` | `DuckDBBridgeClient` | **`mcp_toolbox_client.py` only** |
| `context_layering.py` | `build_context_packet`, `LayeredContext` | U3, U4 |
| `knowledge_base.py` | `load_layered_kb_context` | U3 |
| `failure_diagnostics.py` | `classify` | U3 |
| `types.py` | all dataclasses | All units |
| `config.py` | all settings | All units |
| `events.py` | `emit_event` | All units |

---

## Build Order (Sequential)

1. **U1** — no dependencies; build first
2. **U2** — depends on U1; build second; `duckdb_bridge_client.py` before `mcp_toolbox_client.py` within U2
3. **U3** — depends on U1+U2; build third
4. **U4** — depends on U1+U2+U3; build fourth
5. **U5** — depends on all; build last

## Parallelization Opportunities

Within the unit build order, some modules within a unit can be generated in parallel:

- **U2 parallel group A** (no intra-U2 deps): `knowledge_base.py` || `context_layering.py` || `failure_diagnostics.py` || `duckdb_bridge_client.py`
- **U2 sequential**: `mcp_toolbox_client.py` after `duckdb_bridge_client.py` (reads `tools.yaml`; dispatches DuckDB via `DuckDBBridgeClient`)
- **U4 parallel**: `execution_planner.py` || `result_synthesizer.py` || `sandbox_server.py` + `sandbox_client.py`
- **U5 parallel**: `eval/*.py` || `kb/**/*.md` || `tools.yaml` + `requirements.txt` + supporting files
