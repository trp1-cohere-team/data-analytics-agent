# Deployment Architecture
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11

---

## Runtime Position

```
OS Process: uvicorn (FastAPI)          port 8000
  └── agent/api/app.py  (U1 — AgentAPI)
        └── agent/orchestrator/react_loop.py  (U1 — Orchestrator)
              └── async with MultiDBEngine(mcp_toolbox_url) as engine:
                    └── await engine.execute_plan(plan)
                          ├── asyncio.gather (fan-out)
                          │     ├── PostgreSQLConnector  ──→ HTTP localhost:5000
                          │     ├── SQLiteConnector      ──→ HTTP localhost:5000
                          │     ├── MongoDBConnector     ──→ HTTP localhost:5000
                          │     └── DuckDBConnector      ──→ HTTP localhost:5000
                          ├── JoinKeyResolver  (in-process, no I/O)
                          └── ResultMerger     (in-process, no I/O)

OS Process: MCP Toolbox for Databases  port 5000
  └── tools.yaml → postgres_query / sqlite_query / mongodb_aggregate / duckdb_query
```

---

## Lifecycle

| Event | Action |
|---|---|
| Agent startup (`uvicorn` start) | U1 Orchestrator instantiates `MultiDBEngine`; `__aenter__` creates `aiohttp.ClientSession` and probes `/healthz` |
| MCP Toolbox unreachable at startup | `__aenter__` raises `RuntimeError`; agent logs error; query endpoint returns 503 |
| Per query | `execute_plan` called within existing `async with` block; session reused |
| Agent shutdown | `__aexit__` closes `aiohttp.ClientSession`; all in-flight requests cancelled by uvicorn shutdown |

---

## Environment Variables

All sourced from `agent/config.py` / `.env`:

| Variable | Default | Used By |
|---|---|---|
| `MCP_TOOLBOX_URL` | `http://localhost:5000` | `AiohttpMCPClient` base URL |
| `MAX_RESULT_ROWS` | `1000` | `RowCapGuard` stage-1 and stage-2 |

No new environment variables introduced by U2 beyond what is already in `.env.example`.

---

## Files Produced by U2

```
agent/
  execution/
    __init__.py
    engine.py        ← MultiDBEngine + all internal components
    mcp_client.py    ← AiohttpMCPClient, MCPClient Protocol, ErrorClassifier, MCPHealthProbe
tests/
  unit/
    test_execution_engine.py   ← mocked MCPClient
    test_mcp_client.py         ← ErrorClassifier unit tests
```
