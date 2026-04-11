# U2 Code Generation Plan
# Unit 2 — Multi-DB Execution Engine

**Status**: Complete  
**Date**: 2026-04-11  
**Unit Context**: In-process async library; deploys inside U1's FastAPI process.

---

## Unit Context

**Dependencies**: U5 (agent/models.py, utils/join_key_utils.py)  
**Files Produced**:
- `agent/models.py` — updated with U2-required fields
- `agent/config.py` — updated with `max_result_rows`
- `agent/execution/__init__.py` — package marker
- `agent/execution/mcp_client.py` — MCPClient Protocol, AiohttpMCPClient, ErrorClassifier, MCPHealthProbe
- `agent/execution/engine.py` — MultiDBEngine + all internal components
- `tests/unit/test_mcp_client.py` — ErrorClassifier unit tests
- `tests/unit/test_execution_engine.py` — MultiDBEngine tests (mocked MCPClient)
- `aidlc-docs/construction/u2-multi-db-engine/code/code-summary.md`

**Design Sources**:
- `aidlc-docs/construction/u2-multi-db-engine/functional-design/domain-entities.md`
- `aidlc-docs/construction/u2-multi-db-engine/functional-design/business-logic-model.md`
- `aidlc-docs/construction/u2-multi-db-engine/functional-design/business-rules.md`
- `aidlc-docs/construction/u2-multi-db-engine/nfr-design/nfr-design-patterns.md`
- `aidlc-docs/construction/u2-multi-db-engine/nfr-design/logical-components.md`

---

## Extension Compliance

| Extension | Status | Notes |
|---|---|---|
| Security Baseline | Enforced | No query logging (SEC-U2-03/04), URL from config only (SEC-U2-01) |
| Property-Based Testing | Enforced | PBT properties in test_execution_engine.py and test_mcp_client.py |

---

## Code Generation Steps

- [x] **Step 1** — Update `agent/models.py`  
  Restructure U2 models to match domain-entities.md:
  - `SubQuery`: add `id`, `join_key`, `source_join_format`, `target_join_format`, `join_key_prefix`, `join_key_width`, `join_key_unresolvable`; keep `pipeline`, `collection` (already present)
  - `MergeSpec`: replace current fields with `strategy` (UNION|LEFT_JOIN|FIRST_ONLY), `join_key`, `left_db_type`
  - `QueryPlan`: add `id` field; keep `sub_queries` and `merge_spec`
  - `SubQueryResult`: add `sub_query_id`, `execution_time_ms`, `error`, `row_cap_applied`; keep `db_type`, `rows`, `row_count`
  - `ExecutionResult`: replace with `results`, `merged_rows`, `failures`, `merge_row_cap_applied`
  - `ExecutionFailure`: replace with `sub_query_id`, `db_type`, `error_message`, `error_type`

- [x] **Step 2** — Update `agent/config.py`  
  Add `max_result_rows: int = Field(default=1000, alias="MAX_RESULT_ROWS")` to Settings.

- [x] **Step 3** — Create `agent/execution/__init__.py`  
  Empty package marker exposing `MultiDBEngine` at package level.

- [x] **Step 4** — Create `agent/execution/mcp_client.py`  
  Implements:
  - `MCPClient` Protocol (injectable interface with `call_tool` + `health_check`)
  - `AiohttpMCPClient` — production implementation using shared `aiohttp.ClientSession`
  - `_classify_error(exc, http_status, body) -> str` — 8-type PriorityErrorClassifier
  - `probe_mcp_toolbox(session, base_url, timeout) -> None` — MCPHealthProbe (raises RuntimeError on failure; HTTP 404 = alive)

- [x] **Step 5** — Create `agent/execution/engine.py`  
  Implements (all in one file per deployment-architecture.md):
  - `MultiDBEngine` — top-level; async context manager; owns `aiohttp.ClientSession`
  - `_probe_mcp_toolbox` — EagerConnectionGuard logic (calls `probe_mcp_toolbox` from mcp_client.py)
  - `QueryRouter` — dispatches SubQuery to correct connector via CONNECTOR_MAP
  - `PostgreSQLConnector`, `SQLiteConnector`, `MongoDBConnector`, `DuckDBConnector` — each calls `mcp_client.call_tool`; applies Stage-1 RowCapGuard; logs via ObservabilityEmitter
  - `_execute_sub_query` — wraps connector.execute with `asyncio.wait_for(timeout=30.0)`; catches all exceptions; returns SubQueryResult
  - `JoinKeyResolver` — `pre_execute_resolve` (SQL DBs, in-place query rewrite) + `post_result_resolve` (MongoDB, in-place row transform); delegates to U5 utils
  - `ResultMerger` — `merge(results, spec)` → UNION / LEFT_JOIN / FIRST_ONLY + Stage-2 RowCapGuard
  - `ObservabilityEmitter` — structured logging (emit_complete, emit_failure, emit_join_rewrite, emit_row_cap); never logs row content
  - `execute_plan` — full 6-step pipeline (pre-resolve → fan-out → classify → post-resolve → merge → assemble)

- [x] **Step 6** — Create `tests/unit/test_mcp_client.py`  
  Unit tests for `_classify_error`:
  - All 8 error types hit (timeout, connection_error, rate_limit, auth_error, schema_error, data_type_error, query_error, unknown)
  - Priority order: timeout beats connection_error, etc.
  - Schema keyword variants (table not found, no such table, relation does not exist, etc.)
  - Data type keyword variants (cast, type mismatch, invalid input syntax, etc.)
  - PBT: `classify_error` always returns one of the 8 valid strings (never raises)

- [x] **Step 7** — Create `tests/unit/test_execution_engine.py`  
  Unit tests for MultiDBEngine using injected mock MCPClient:
  - `execute_plan` success path (all sub-queries succeed, UNION merge)
  - Partial failure: one sub-query fails, others succeed → failures populated, merged_rows from successful only
  - LEFT_JOIN strategy: correct row matching, unmatched left rows get `{}` fill
  - FIRST_ONLY strategy: returns first non-empty success
  - Stage-1 RowCapGuard: rows truncated per-connector when len > max_result_rows
  - Stage-2 RowCapGuard: merged_rows truncated post-merge when len > max_result_rows
  - EagerConnectionGuard: `__aenter__` raises RuntimeError when health check fails
  - JoinKeyResolver: pre_execute_resolve rewrites SQL query; post_result_resolve transforms MongoDB rows
  - PBT: `execute_plan` with valid plan always returns ExecutionResult with `len(results) == len(plan.sub_queries)`

- [x] **Step 8** — Create `aidlc-docs/construction/u2-multi-db-engine/code/code-summary.md`  
  Markdown summary of all generated files, key design decisions, and PBT properties.

---

## Completion Criteria

- All 8 steps marked [x]
- All application code in `agent/` (never in aidlc-docs/)
- Security rules: no row content in logs, no hardcoded URLs
- PBT properties present in both test files
- All U2 design decisions implemented as specified (Q1=D, Q2=B, Q3=C, Q4=A for functional; Q1=B, Q2=C for NFR)
