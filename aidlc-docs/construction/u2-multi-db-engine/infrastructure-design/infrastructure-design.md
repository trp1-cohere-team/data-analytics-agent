# Infrastructure Design
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11

---

## Infrastructure Category Assessment

| Category | Status | Justification |
|---|---|---|
| Deployment Environment | N/A | U2 is an in-process library; deploys as part of U1's FastAPI process — no separate deployment unit |
| Compute Infrastructure | N/A | Runs inside U1's process; compute sizing is a U1 concern |
| Storage Infrastructure | N/A | MultiDBEngine is stateless; it reads from external DBs via MCP Toolbox, writes nothing |
| Messaging Infrastructure | N/A | Synchronous request/response only; `asyncio.gather` for fan-out is in-process, not a message queue |
| Networking Infrastructure | N/A — shared | Only external network touch: `localhost:5000` HTTP to MCP Toolbox; fully documented in `construction/shared-infrastructure.md` |
| Monitoring Infrastructure | N/A | ObservabilityEmitter uses Python stdlib `logging`; no dedicated monitoring service; log aggregation is an operational concern outside project scope |
| Shared Infrastructure | Documented | MCP Toolbox (localhost:5000) is the sole shared dependency; spec is in `construction/shared-infrastructure.md` |

---

## Summary

U2 has **no standalone infrastructure requirements**. It is an async in-process library that:

1. Runs inside U1's FastAPI server process (single-process deployment)
2. Communicates with MCP Toolbox over localhost HTTP (documented in shared-infrastructure.md)
3. Manages its own `aiohttp.ClientSession` lifecycle via async context manager — no connection pool service needed
4. Writes no data — fully stateless between `execute_plan` calls

The one runtime dependency — MCP Toolbox for Databases — is shared with U5 (SchemaIntrospector) and its configuration (`tools.yaml`, `MCP_TOOLBOX_URL` env var) is already established.

---

## Shared Infrastructure Reference

See [construction/shared-infrastructure.md](../../shared-infrastructure.md) for:
- MCP Toolbox process startup command
- `tools.yaml` connector configuration
- Required environment variables (`MCP_TOOLBOX_URL`)
- Per-DB connection details (PostgreSQL, SQLite, MongoDB, DuckDB)
