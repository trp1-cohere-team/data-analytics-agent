# U2 NFR Requirements Plan
# Unit 2 — Multi-DB Execution Engine

**Status**: Complete  
**Date**: 2026-04-11

---

## NFR Assessment Steps

- [x] Q1 answered: Result size cap (D — configurable from config.py, default 1000)
- [x] Q2 answered: aiohttp session strategy (C — per-engine-instance, async context manager)
- [x] Q3 answered: Error type classification (B — 8 types, parse error body)
- [x] Generate nfr-requirements.md
- [x] Generate tech-stack-decisions.md

---

## Questions

### Q1 — Result Size Cap

Each DB connector returns `list[dict]` from MCP Toolbox. A single MongoDB aggregation or DuckDB analytical query could return tens of thousands of rows. Should the engine enforce a per-sub-query row cap?

**A** — No cap: return all rows the DB produces; let the caller (Orchestrator) handle large results  
**B** — Soft cap: log a warning if rows > 1000, but return all rows  
**C** — Hard cap: truncate to 1000 rows per sub-query; add `row_cap_applied: bool` field to SubQueryResult so caller knows data was truncated  
**D** — Configurable cap: read max rows from `config.py` (default 1000); hard truncate at that value

[Answer Q1]: D

---

### Q2 — aiohttp Session Strategy

`aiohttp.ClientSession` is the HTTP client for MCP Toolbox calls. Sessions can be created per-request (simple, no state) or reused across requests (connection pooling, faster).

**A** — Per-request session: create a new `ClientSession` for each `execute_plan` call; close it after; simple lifecycle, no pooling  
**B** — Module-level singleton session: one `ClientSession` created at import time, reused for all calls; provides TCP connection reuse; must handle session closure on app shutdown  
**C** — Per-engine-instance session: `MultiDBEngine.__init__` creates and owns one session; session is closed when engine is garbage-collected or explicitly closed; supports async context manager (`async with MultiDBEngine(...) as engine`)

[Answer Q2]: C

---

### Q3 — Error Type Classification

`ExecutionFailure.error_type` categorises failures for the CorrectionEngine upstream. How granular should classification be?

**A** — Simple (4 types): `"timeout"` | `"connection_error"` | `"query_error"` | `"unknown"` — classified by exception type only  
**B** — Detailed (8 types): additionally distinguishes `"auth_error"`, `"schema_error"` (table/column not found), `"data_type_error"` (cast failure), `"rate_limit"` — parsed from the MCP Toolbox error message body  
**C** — Simple types only, but include the raw MCP Toolbox HTTP status code and error body in the `error_message` string so CorrectionEngine can do its own parsing if needed

[Answer Q3]: B

---
