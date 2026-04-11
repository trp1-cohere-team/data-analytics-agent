# Business Rules
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11

---

## Execution Rules

| ID | Rule | Source |
|---|---|---|
| EE-01 | All DB calls must use async aiohttp; no synchronous blocking I/O permitted | NFR-02, architecture |
| EE-02 | Each sub-query has a 30-second timeout; `asyncio.TimeoutError` → `SubQueryResult` with `error="timeout_30s"` | Application Design |
| EE-03 | All exceptions caught inside `_execute_sub_query`; raw exceptions never propagate to `MultiDBEngine.execute_plan` caller | Architecture |
| EE-04 | Partial failure permitted (Q2=B): failed sub-queries produce `SubQueryResult.error`; remaining sub-queries continue and their results are returned | Q2 answer |
| EE-05 | Sub-queries fan out concurrently via `asyncio.gather(..., return_exceptions=True)` | Architecture |
| EE-06 | `MergeSpec.strategy` is the sole determinant of merge algorithm; the engine never infers strategy from result shape | Q1 answer |

---

## Merge Rules

| ID | Rule | Source |
|---|---|---|
| EE-07 | UNION strategy: extend results from all non-failed sub-queries into a flat list; failed sub-queries contribute no rows | Q1 answer |
| EE-08 | LEFT_JOIN strategy: all rows from the left sub-query (identified by `MergeSpec.left_db_type`) are preserved; right-side rows matching on `join_key` are merged in; unmatched left rows get `{}` fill for right columns | Q1 answer (D = LEFT_JOIN) |
| EE-09 | LEFT_JOIN: when multiple right rows match one left key value, one merged row is produced per right match (cartesian expansion) | EE-08 implication |
| EE-10 | LEFT_JOIN: if the left sub-query itself failed, return `[]` — an empty left side cannot be joined | Q2=B + EE-08 |
| EE-11 | FIRST_ONLY strategy: return rows from the first `SubQueryResult` where `error is None` and `rows` is non-empty; order follows `plan.sub_queries` list order | Q1 answer |
| EE-12 | `SubQueryResult.rows` is always `list[dict[str, Any]]`; empty list `[]` when no rows returned or sub-query failed — never `None` | Data contract |

---

## MongoDB Rules

| ID | Rule | Source |
|---|---|---|
| EE-13 | MongoDB sub-query pipeline is passed through unchanged to MCP Toolbox `mongodb_aggregate`; MultiDBEngine performs no pipeline translation (Q4=A) | Q4 answer |
| EE-14 | `SubQuery.collection` is required for all MongoDB sub-queries; absence → `SubQueryResult` error before any network call | Data contract |
| EE-15 | MongoDB pipeline is always `list[dict]`; if the Orchestrator provides it as a JSON string, it must be parsed before passing to MCPClient | Data validation |

---

## MCP Toolbox Rules

| ID | Rule | Source |
|---|---|---|
| EE-16 | MCP Toolbox URL sourced exclusively from `config.mcp_toolbox_url`; never hardcoded | Security Baseline |
| EE-17 | MCP Toolbox runs on localhost only; no auth header required | Architecture |
| EE-18 | MCPClient connection error (refused / unreachable) → `SubQueryResult` with error; never crashes the engine | EE-03 |
| EE-19 | MCPClient uses a single `aiohttp.ClientSession` per `execute_plan` call; sessions not reused across calls | Resource management |

---

## JoinKeyResolver Rules

| ID | Rule | Source |
|---|---|---|
| EE-20 | Pre-execution phase applies only to SQL-based DBs: `postgres`, `sqlite`, `duckdb`; MongoDB is excluded (Q3=C) | Q3 answer |
| EE-21 | Post-result phase applies only to MongoDB `SubQueryResult`s where `join_key` is set and `error is None` | Q3 answer |
| EE-22 | `JoinKeyUtils.build_transform_expression` returning `None` (unsupported pair) marks `SubQuery.join_key_unresolvable = True`; the sub-query still executes unchanged — resolution failure is non-blocking | EE-04 principle |
| EE-23 | `JoinKeyUtils.transform_key` returning `None` (unsupported pair) in post-result phase: leave the row value unchanged; do not raise | EE-03 principle |
| EE-24 | JoinKeyResolver never raises exceptions; all errors are surfaced via the `join_key_unresolvable` flag or silent pass-through | NullReturnGuard pattern (U5) |
| EE-25 | `detect_format` is called with all join-key column values from the result set, not just the first row | U5 API contract |

---

## QueryRouter Rules

| ID | Rule | Rule |
|---|---|---|
| EE-26 | Unknown `db_type` values → `SubQueryResult` with error `"unknown_db_type:{db_type}"`; never raise to caller | EE-03 |
| EE-27 | Connector instances are created per `execute_plan` call; no connector state is shared across requests | Concurrency safety |

---

## Data Integrity Rules

| ID | Rule | Source |
|---|---|---|
| EE-28 | `ExecutionResult.merged_rows` is `[]` when all sub-queries fail or merge strategy produces no rows — never `None` | Data contract |
| EE-29 | `ExecutionResult.failures` contains one `ExecutionFailure` per failed `SubQueryResult`; order matches `plan.sub_queries` order | Data contract |
| EE-30 | `SubQueryResult.execution_time_ms` is always populated (0 on instant failure); never `None` | Observability |
