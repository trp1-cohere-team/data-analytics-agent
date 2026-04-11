# Domain Entities
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11  
**Source**: `agent/models.py` (shared models — defined in U5/shared infra, consumed here)

---

## Entity: SubQuery

**Purpose**: A single database query targeting one DB type. The atomic unit of a QueryPlan.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | Unique within the plan (UUID) |
| `db_type` | `str` | `"postgres"` \| `"sqlite"` \| `"mongodb"` \| `"duckdb"` |
| `query` | `str` | SQL string for SQL DBs; ignored for MongoDB |
| `pipeline` | `list[dict] \| None` | MongoDB aggregation pipeline (pre-built by LLM, Q4=A); `None` for SQL DBs |
| `collection` | `str \| None` | MongoDB collection name; required if db_type == "mongodb" |
| `db_name` | `str` | Target database/file name for routing |
| `join_key` | `str \| None` | Column name used for cross-DB join; `None` if this sub-query is not part of a join |
| `source_join_format` | `JoinKeyFormat \| None` | Format of the join key in this sub-query's DB |
| `target_join_format` | `JoinKeyFormat \| None` | Format expected by the joining sub-query |
| `join_key_prefix` | `str \| None` | PREFIXED_STRING prefix (e.g. "CUST") for JoinKeyResolver |
| `join_key_width` | `int \| None` | Zero-padding width for JoinKeyResolver |
| `join_key_unresolvable` | `bool` | Set by JoinKeyResolver when format pair is unsupported (EE-22) |

**Invariants**:
- `db_type in ("postgres", "sqlite", "mongodb", "duckdb")`
- If `db_type == "mongodb"`: `pipeline` is `list[dict]` and `collection` is non-empty
- If `join_key` is set: `source_join_format` and `target_join_format` must also be set

---

## Entity: MergeSpec

**Purpose**: Specifies how results from multiple sub-queries are combined.

| Field | Type | Notes |
|---|---|---|
| `strategy` | `str` | `"UNION"` \| `"LEFT_JOIN"` \| `"FIRST_ONLY"` |
| `join_key` | `str \| None` | Column name to join on; required for `LEFT_JOIN` |
| `left_db_type` | `str \| None` | The `db_type` whose result is the left (preserved) side of `LEFT_JOIN` |

**Invariants**:
- If `strategy == "LEFT_JOIN"`: `join_key` and `left_db_type` must be non-None
- If `strategy == "FIRST_ONLY"`: `join_key` and `left_db_type` are ignored

---

## Entity: QueryPlan

**Purpose**: The complete execution plan for one agent query — contains all sub-queries and how to merge them.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | Plan UUID (matches session query) |
| `sub_queries` | `list[SubQuery]` | Ordered list of DB sub-queries |
| `merge_spec` | `MergeSpec` | How to combine sub-query results |

**Invariants**:
- `len(sub_queries) >= 1`
- All `sub_query.id` values are unique within the plan

---

## Entity: SubQueryResult

**Purpose**: The outcome of executing one SubQuery — success or failure.

| Field | Type | Notes |
|---|---|---|
| `sub_query_id` | `str` | References `SubQuery.id` |
| `db_type` | `str` | Copied from `SubQuery.db_type` (for routing in post-result phase) |
| `rows` | `list[dict[str, Any]]` | Result rows; always `[]` on failure — never `None` (EE-12) |
| `row_count` | `int` | `len(rows)` |
| `execution_time_ms` | `float` | Wall-clock time for the sub-query (0.0 on instant error) |
| `error` | `str \| None` | Error description if failed; `None` on success |

**Derived**:
- `is_success: bool = error is None`

---

## Entity: ExecutionResult

**Purpose**: The complete outcome of executing a QueryPlan — merged rows + per-sub-query results + failure summary.

| Field | Type | Notes |
|---|---|---|
| `results` | `list[SubQueryResult]` | One entry per SubQuery; preserves plan order |
| `merged_rows` | `list[dict[str, Any]]` | Output of ResultMerger; `[]` if all failed or merge produced no rows |
| `failures` | `list[ExecutionFailure]` | One per failed SubQueryResult; `[]` if all succeeded |

**Invariants**:
- `len(results) == len(plan.sub_queries)`
- `merged_rows` is never `None`
- `failures` is never `None`

---

## Entity: ExecutionFailure

**Purpose**: Structured description of a single sub-query failure for upstream consumption (CorrectionEngine).

| Field | Type | Notes |
|---|---|---|
| `sub_query_id` | `str` | References the failed `SubQuery.id` |
| `db_type` | `str` | Which DB type failed |
| `error_message` | `str` | Human-readable error description |
| `error_type` | `str` | Classification: `"timeout"` \| `"connection_error"` \| `"query_error"` \| `"unknown_db_type"` \| `"unknown"` |

---

## Entity: MCPToolboxRequest (Internal)

**Purpose**: The payload sent to MCP Toolbox for one DB call.

| DB Type | Tool Name | Payload Fields |
|---|---|---|
| postgres | `postgres_query` | `{"query": str}` |
| sqlite | `sqlite_query` | `{"query": str}` |
| duckdb | `duckdb_query` | `{"query": str}` |
| mongodb | `mongodb_aggregate` | `{"pipeline": list[dict], "collection": str}` |

**Response contract**: `{"result": list[dict]}` — always a list of row/document dicts.

---

## Entity Relationships

```
QueryPlan
  ├── sub_queries: list[SubQuery]      (1..N)
  └── merge_spec: MergeSpec            (1)

MultiDBEngine.execute_plan(QueryPlan)
  ├── JoinKeyResolver.pre_execute_resolve(QueryPlan)
  │     └─ rewrites SubQuery.query (SQL DBs only)
  ├── asyncio.gather → list[SubQueryResult]
  ├── JoinKeyResolver.post_result_resolve (MongoDB only)
  ├── ResultMerger.merge → list[dict]
  └── ExecutionResult
        ├── results: list[SubQueryResult]
        ├── merged_rows: list[dict]
        └── failures: list[ExecutionFailure]
```

---

## JoinKeyResolver State

The JoinKeyResolver carries no persistent state. All decisions are computed from:
- `SubQuery.source_join_format` / `SubQuery.target_join_format` (pre-execution)
- `detect_format(key_values)` on live result rows (post-result, MongoDB)

This makes it a stateless, pure-logic component consistent with U5 JoinKeyUtils (pure functions).
