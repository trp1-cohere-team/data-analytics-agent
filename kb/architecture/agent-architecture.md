# OracleForge Agent Architecture

## Overview
OracleForge is a multi-database analytics agent evaluated against DataAgentBench (DAB).
It uses a 6-layer context pipeline, unified MCP tool interface, and a self-correction loop.

## Layer Architecture (FR-02)

| Layer | Name | Source | Precedence |
|-------|------|--------|-----------|
| 6 | User question | Current input | Highest |
| 5 | Interaction memory | Session history + corrections log | |
| 4 | Runtime context | Session ID, tools, selected DB, flags | |
| 3 | Institutional knowledge | kb/architecture + kb/evaluation + AGENT.md | |
| 2 | Human annotations | kb/domain (query-aware retrieval) | |
| 1 | Table usage | DB schema, join hints | Lowest |

Layer 6 always overrides Layer 1. Higher layers take precedence during prompt assembly.

## Tool Routing (FR-03)

All 4 database tools appear as a flat list to upstream components. Dispatch is internal to MCPClient:

```
MCPClient.invoke_tool(name, params)
  ├── kind in {postgres-sql, mongodb-aggregate, sqlite-sql}
  │     └── → Google MCP Toolbox (MCP_TOOLBOX_URL)
  └── kind == duckdb_bridge_sql
        └── → DuckDBBridgeClient (DUCKDB_BRIDGE_URL)
```

## Self-Correction Loop (FR-04)

1. Execute tool call
2. On failure: `failure_diagnostics.classify()` → category
3. `execution_planner.propose_correction()` → correction string
4. Write to kb/corrections/corrections_log.md
5. Retry (max `AGENT_SELF_CORRECTION_RETRIES`)

Categories: `query` | `join-key` | `db-type` | `data-quality`

## Offline Mode (NFR-01)

`AGENT_OFFLINE_MODE=1` enables deterministic stubs:
- LLM: returns `OFFLINE_LLM_RESPONSE` from config.py
- MCP tools: returns `OFFLINE_INVOKE_RESULTS` (keyed by db_type)
- No network calls made

## Module Dependency Order

```
U1 Foundation (types, config, events, utils)
  └── U2 Data Layer (knowledge_base, context_layering, failure_diagnostics, MCPClient)
        └── U3 Runtime Layer (memory, tooling, conductor)
              └── U4 Agent + Sandbox (execution_planner, result_synthesizer, oracle_forge_agent)
                    └── U5 Eval + Supporting (eval/, kb/, tests/, tools.yaml)
```
