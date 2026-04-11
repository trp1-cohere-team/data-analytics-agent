# U2 NFR Design Plan
# Unit 2 — Multi-DB Execution Engine

**Status**: Complete  
**Date**: 2026-04-11

---

## NFR Design Steps

- [x] Q1 answered: Session lifecycle on MCP failure (B — eager health check in __aenter__)
- [x] Q2 answered: Row cap application point (C — both per-sub-query and post-merge)
- [x] Generate nfr-design-patterns.md
- [x] Generate logical-components.md

---

## Questions

### Q1 — Session Lifecycle on MCP Toolbox Failure

`MultiDBEngine` uses a per-instance `aiohttp.ClientSession` (created in `__aenter__`). If MCP Toolbox is unreachable, when should the failure surface?

**A** — Lazy (fail on first call): `__aenter__` creates the session object but does NOT test connectivity; the first `call_tool` inside `execute_plan` surfaces the connection error as a `SubQueryResult` error — engine stays alive  
**B** — Eager health check: `__aenter__` sends a lightweight `GET /healthz` to MCP Toolbox; if unreachable, `__aenter__` raises `RuntimeError` immediately — engine never enters usable state

[Answer Q1]: B

---

### Q2 — Row Cap Application Point

`MAX_RESULT_ROWS` (default 1000) truncates results. Where should the cap be applied?

**A** — Per-sub-query only: each connector truncates its own rows to `MAX_RESULT_ROWS` before returning; merged result may therefore contain up to `N × MAX_RESULT_ROWS` rows (where N = number of sub-queries)  
**B** — Post-merge only: connectors return all rows; `ResultMerger` truncates the final merged list to `MAX_RESULT_ROWS` after combining  
**C** — Both: per-sub-query cap prevents memory spike during `asyncio.gather` (each result bounded); post-merge cap bounds the final output seen by the Orchestrator

[Answer Q2]: C

---
