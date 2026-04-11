# Business Logic Model
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11  
**Design Decisions**: Q1=D (UNION+LEFT_JOIN+FIRST_ONLY), Q2=B (partial failure), Q3=C (pre+post), Q4=A (pass-through pipeline)

---

## 1. Top-Level Algorithm: execute_plan

`MultiDBEngine.execute_plan(plan: QueryPlan) → ExecutionResult`

```
1. PRE-EXECUTION RESOLVE
   JoinKeyResolver.pre_execute_resolve(plan)
     └─ For each cross-DB SubQuery pair where join_key is set:
          a. Retrieve key format hints from SubQuery.expected_join_format (if provided)
          b. If not provided, detect_format(key_samples) on known schema context values
          c. If source_fmt ≠ target_fmt (mismatch detected):
               - call build_transform_expression(join_col, src_fmt, tgt_fmt, db_type)
               - if expression is not None: rewrite SubQuery.query with the transform expression
               - if expression is None (unsupported pair): mark SubQuery.join_key_unresolvable = True
          d. Only rewrites SQL-based DBs (postgres, sqlite, duckdb)
          e. MongoDB sub-queries: skip pre-execution (handled post-result)

2. FAN-OUT EXECUTION
   raw_results = await asyncio.gather(
       *[_execute_sub_query(sq) for sq in plan.sub_queries],
       return_exceptions=True
   )

3. CLASSIFY RESULTS
   For each (sub_query, raw_result) pair:
     if raw_result is Exception:
         → SubQueryResult(error=str(raw_result), rows=[])
     else:
         → raw_result (SubQueryResult as returned)

4. POST-RESULT RESOLVE (MongoDB only)
   JoinKeyResolver.post_result_resolve(sub_query_results, plan)
     └─ For each SubQueryResult where db_type == "mongodb" and join_key is set:
          a. Extract key column values from result rows
          b. detect_format(key_values) → actual_fmt
          c. If actual_fmt ≠ target_fmt (other DB's format):
               - apply transform_key(value, actual_fmt, target_fmt) to each row's join_key value
               - if transform_key returns None: leave value as-is (log warning)

5. MERGE
   merged_rows = ResultMerger.merge(sub_query_results, plan.merge_spec)

6. ASSEMBLE ExecutionResult
   failures = [SubQueryResult.to_failure() for r in sub_query_results if r.error]
   return ExecutionResult(
       results=sub_query_results,
       merged_rows=merged_rows,
       failures=failures,
   )
```

---

## 2. Sub-Query Execution: _execute_sub_query

`_execute_sub_query(sub_query: SubQuery) → SubQueryResult`

```
start_time = now()
try:
    connector = QueryRouter.get_connector(sub_query.db_type)
    rows = await asyncio.wait_for(
        connector.execute(sub_query),
        timeout=30.0          # EE-02: 30s per sub-query
    )
    return SubQueryResult(
        sub_query_id=sub_query.id,
        rows=rows,
        row_count=len(rows),
        execution_time_ms=elapsed_ms(start_time),
        error=None,
    )
except asyncio.TimeoutError:
    return SubQueryResult(..., error="timeout_30s", rows=[])
except Exception as exc:
    return SubQueryResult(..., error=str(exc), rows=[])
# EE-03: all exceptions wrapped — none propagate
```

---

## 3. QueryRouter: get_connector

```
CONNECTOR_MAP = {
    "postgres": PostgreSQLConnector,
    "sqlite":   SQLiteConnector,
    "mongodb":  MongoDBConnector,
    "duckdb":   DuckDBConnector,
}

def get_connector(db_type: str) → Connector:
    connector_cls = CONNECTOR_MAP.get(db_type)
    if connector_cls is None:
        raise ValueError(f"Unknown db_type: {db_type}")
    return connector_cls(mcp_client)
```

---

## 4. DB Connectors

### PostgreSQLConnector

```
async execute(sub_query: SubQuery) → list[dict]:
    result = await mcp_client.call_tool("postgres_query", {
        "query": sub_query.query
    })
    return result["result"]    # list of row dicts
```

### SQLiteConnector

```
async execute(sub_query: SubQuery) → list[dict]:
    result = await mcp_client.call_tool("sqlite_query", {
        "query": sub_query.query
    })
    return result["result"]
```

### MongoDBConnector

```
async execute(sub_query: SubQuery) → list[dict]:
    # Q4=A: pipeline is pre-built by LLM; pass through unchanged
    result = await mcp_client.call_tool("mongodb_aggregate", {
        "pipeline": sub_query.pipeline,          # list[dict] — MongoDB aggregation stages
        "collection": sub_query.collection,      # required for MongoDB
    })
    return result.get("result", [])
```

### DuckDBConnector

```
async execute(sub_query: SubQuery) → list[dict]:
    result = await mcp_client.call_tool("duckdb_query", {
        "query": sub_query.query
    })
    return result["result"]
```

---

## 5. ResultMerger

`ResultMerger.merge(results: list[SubQueryResult], spec: MergeSpec) → list[dict]`

### Strategy: UNION

```
merged = []
for r in results:
    if r.error is None:             # skip failed sub-queries
        merged.extend(r.rows)
return merged
```

### Strategy: LEFT_JOIN

```
Requires: spec.join_key, spec.left_db_type

left  = next(r for r in results if r.sub_query.db_type == spec.left_db_type and r.error is None)
right_rows_by_key = {}
for r in results:
    if r.sub_query.db_type != spec.left_db_type and r.error is None:
        for row in r.rows:
            key_val = row.get(spec.join_key)
            right_rows_by_key.setdefault(key_val, []).append(row)

merged = []
for left_row in left.rows:
    key_val = left_row.get(spec.join_key)
    right_matches = right_rows_by_key.get(key_val, [{}])  # [{}] = NULL fill
    for right_row in right_matches:
        merged.append({**left_row, **right_row})           # right overwrites on collision
return merged
```

### Strategy: FIRST_ONLY

```
for r in results:
    if r.error is None and r.rows:
        return r.rows               # first non-empty success wins
return []
```

---

## 6. JoinKeyResolver: Pre-Execution Rewrite

`pre_execute_resolve(plan: QueryPlan) → None`  (mutates SubQuery.query in-place)

```
sql_sub_queries = [sq for sq in plan.sub_queries if sq.db_type in ("postgres","sqlite","duckdb")]

for sq in sql_sub_queries:
    if sq.join_key is None:
        continue
    src_fmt = sq.source_join_format    # provided by Orchestrator or inferred
    tgt_fmt = sq.target_join_format    # format expected by the other side
    if src_fmt == tgt_fmt:
        continue                        # no mismatch
    expr = build_transform_expression(sq.join_key, src_fmt, tgt_fmt, sq.db_type,
                                      prefix=sq.join_key_prefix, width=sq.join_key_width)
    if expr is not None:
        # Replace join key column reference in SQL with the transform expression
        sq.query = sq.query.replace(sq.join_key, expr, 1)
    else:
        sq.join_key_unresolvable = True    # signal upstream that join may produce empty results
```

---

## 7. JoinKeyResolver: Post-Result Transform (MongoDB)

`post_result_resolve(results: list[SubQueryResult], plan: QueryPlan) → None`  (mutates rows in-place)

```
for result in results:
    sq = result.sub_query
    if sq.db_type != "mongodb" or sq.join_key is None or result.error:
        continue
    key_values = [row[sq.join_key] for row in result.rows if sq.join_key in row]
    if not key_values:
        continue
    actual_fmt = detect_format(key_values).primary_format
    tgt_fmt = sq.target_join_format
    if actual_fmt == tgt_fmt:
        continue
    for row in result.rows:
        if sq.join_key in row:
            transformed = transform_key(row[sq.join_key], actual_fmt, tgt_fmt,
                                        prefix=sq.join_key_prefix, width=sq.join_key_width)
            if transformed is not None:
                row[sq.join_key] = transformed
            # else: leave unchanged (unsupported pair)
```
