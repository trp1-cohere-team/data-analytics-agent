# Code Summary
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11  
**Status**: Complete

---

## Generated Files

| File | Type | Purpose |
|---|---|---|
| `agent/models.py` | Modified | Added 7 fields to SubQuery; replaced MergeSpec, SubQueryResult, ExecutionResult, ExecutionFailure with design-spec versions |
| `agent/config.py` | Modified | Added `max_result_rows: int = 1000` (env: `MAX_RESULT_ROWS`) |
| `agent/execution/__init__.py` | Created | Package marker; exports `MultiDBEngine` |
| `agent/execution/mcp_client.py` | Created | MCPClient Protocol, AiohttpMCPClient, _classify_error, probe_mcp_toolbox |
| `agent/execution/engine.py` | Created | MultiDBEngine + all 8 internal components (see component table) |
| `tests/unit/test_mcp_client.py` | Created | 20 unit tests + PBT-U2-MC-01 for ErrorClassifier and MCPHealthProbe |
| `tests/unit/test_execution_engine.py` | Created | 18 unit tests + PBT-U2-EE-01 for MultiDBEngine (mocked MCPClient) |

---

## Internal Components (engine.py)

| Component | Class / Function | Role |
|---|---|---|
| ObservabilityEmitter | `_ObservabilityEmitter` | Structured logging — emit_complete, emit_failure, emit_join_rewrite, emit_row_cap |
| RowCapGuard (stage-1) | `_apply_per_subquery_cap` | Truncates rows per connector (bounds asyncio.gather memory) |
| RowCapGuard (stage-2) | `_apply_merge_cap` | Truncates merged result (bounds Orchestrator / LLM context) |
| PostgreSQLConnector | `_PostgreSQLConnector` | Calls `postgres_query` tool; applies stage-1 cap |
| SQLiteConnector | `_SQLiteConnector` | Calls `sqlite_query` tool; applies stage-1 cap |
| MongoDBConnector | `_MongoDBConnector` | Calls `mongodb_aggregate` with pipeline+collection pass-through (Q4=A) |
| DuckDBConnector | `_DuckDBConnector` | Calls `duckdb_query` tool; applies stage-1 cap |
| QueryRouter | `_QueryRouter` | Dispatches SubQuery.db_type → correct connector via CONNECTOR_MAP |
| JoinKeyResolver | `_JoinKeyResolver` | Pre-exec SQL rewrite (Q3=C) + post-result MongoDB transform |
| ResultMerger | `_ResultMerger` | UNION / LEFT_JOIN / FIRST_ONLY strategies + stage-2 cap |
| MultiDBEngine | `MultiDBEngine` | Top-level async context manager; owns aiohttp.ClientSession |

---

## Key Design Decisions Implemented

| Decision | Implementation |
|---|---|
| **Q1=D**: UNION+LEFT_JOIN+FIRST_ONLY | `_ResultMerger._union`, `_left_join`, `_first_only` |
| **Q2=B**: Partial failure continuation | `asyncio.gather(return_exceptions=True)` + per-result error wrapping |
| **Q3=C**: Pre-exec (SQL) + post-result (MongoDB) join key resolve | `_JoinKeyResolver.pre_execute_resolve` + `post_result_resolve` |
| **Q4=A**: MongoDB pipeline pass-through | `_MongoDBConnector.execute` passes `sq.pipeline` + `sq.collection` unchanged |
| **NFR Q1=B**: EagerConnectionGuard | `probe_mcp_toolbox` called in `MultiDBEngine.__aenter__`; raises RuntimeError immediately |
| **NFR Q2=C**: DoubleRowCapGuard | Stage-1 in each connector; Stage-2 in `_ResultMerger.merge` |
| **8-type PriorityErrorClassifier** | `_classify_error` in mcp_client.py; priority-ordered, first-match wins |
| **StructuredObservabilityEmitter** | `_ObservabilityEmitter`; never logs row content (SEC-U2-03/04) |

---

## PBT Invariant Properties

| ID | Location | Property |
|---|---|---|
| PBT-U2-MC-01 | `test_mcp_client.py` | `_classify_error` always returns one of 8 valid strings; never raises |
| PBT-U2-EE-01 | `test_execution_engine.py` | `execute_plan` always returns `len(results) == len(plan.sub_queries)` |

---

## Security Rules Compliance

| Rule | Status | Implementation |
|---|---|---|
| SEC-U2-01: URL from config only | Compliant | `mcp_toolbox_url` sourced from `settings`; never hardcoded in engine/client |
| SEC-U2-02: No raw exception propagation to API | Compliant | All exceptions caught in `_execute_sub_query`; returned as SubQueryResult.error |
| SEC-U2-03: No query text logging | Compliant | ObservabilityEmitter logs only counts/IDs/types/timings |
| SEC-U2-04: No row content logging | Compliant | Row content never passed to logger in any component |

---

## U5 Dependencies Used

| U5 Utility | Used In | Purpose |
|---|---|---|
| `utils.join_key_utils.build_transform_expression` | `_JoinKeyResolver.pre_execute_resolve` | Build SQL expression to normalize join key format |
| `utils.join_key_utils.detect_format` | `_JoinKeyResolver.post_result_resolve` | Detect actual join key format from MongoDB result rows |
| `utils.join_key_utils.transform_key` | `_JoinKeyResolver.post_result_resolve` | Apply format transform to individual MongoDB row values |
