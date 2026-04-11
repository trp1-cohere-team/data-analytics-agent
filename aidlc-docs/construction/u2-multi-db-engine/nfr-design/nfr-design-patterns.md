# NFR Design Patterns
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11  
**NFR Decisions**: Q1=B (eager health check), Q2=C (dual row cap)

---

## Pattern 1: EagerConnectionGuard

**Addresses**: RES-U2-02 (session creation in `__aenter__`), Q1=B (fail-fast on MCP Toolbox unreachable)

**Problem**: A misconfigured or down MCP Toolbox would cause every sub-query in `execute_plan` to fail individually with `SubQueryResult.error`. The caller (CorrectionEngine) would receive an ExecutionResult full of failures with no clear root cause — the agent would waste a full ReAct iteration discovering a systemic connectivity problem.

**Solution**: `MultiDBEngine.__aenter__` runs a lightweight health probe against MCP Toolbox *before* entering the usable engine state. If the probe fails, `__aenter__` raises `RuntimeError` immediately, preventing `execute_plan` from being called at all. The caller (Orchestrator) catches this at engine creation time and can surface it as a configuration error rather than a query failure.

**Implementation**:
```python
async def __aenter__(self) -> "MultiDBEngine":
    self._session = aiohttp.ClientSession()
    await self._probe_mcp_toolbox()        # raises RuntimeError on failure
    return self

async def _probe_mcp_toolbox(self) -> None:
    url = self._mcp_url.rstrip("/") + "/healthz"
    try:
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
            if resp.status >= 500:
                raise RuntimeError(f"MCP Toolbox unhealthy: HTTP {resp.status}")
    except aiohttp.ClientConnectionError as exc:
        raise RuntimeError(f"MCP Toolbox unreachable at {self._mcp_url}: {exc}") from exc
    except asyncio.TimeoutError:
        raise RuntimeError(f"MCP Toolbox health check timed out (3s) at {self._mcp_url}")

async def __aexit__(self, *args: Any) -> None:
    if self._session and not self._session.closed:
        await self._session.close()
```

**Tradeoffs**:
- Adds ~3s latency at engine startup if MCP is slow but alive (acceptable — agent startup, not per-query)
- If MCP Toolbox has no `/healthz` endpoint: probe falls back to catching HTTP 404 as "alive but no health route" → probe passes (connection confirmed)

---

## Pattern 2: DoubleRowCapGuard

**Addresses**: PERF-U2-03, PERF-U2-04, PERF-U2-05, Q2=C

**Problem**: A single MongoDB aggregation or DuckDB analytical query can return 100K+ rows. With `asyncio.gather` fanning out multiple sub-queries simultaneously, the peak memory footprint is `sum(row_count_per_subquery)`. After merging, the Orchestrator (and ultimately the LLM context window) receives the combined result.

**Solution**: Two-stage capping:

**Stage 1 — Per-SubQuery Cap** (inside each DB connector):
```python
rows = result["result"]
cap = self._max_result_rows           # from config
if len(rows) > cap:
    rows = rows[:cap]
    row_cap_applied = True
else:
    row_cap_applied = False
return SubQueryResult(rows=rows, row_cap_applied=row_cap_applied, ...)
```
- Bounds memory during `asyncio.gather` to `N × MAX_RESULT_ROWS` (N = sub-query count)
- `SubQueryResult.row_cap_applied = True` signals upstream that data was truncated

**Stage 2 — Post-Merge Cap** (inside ResultMerger, after combining):
```python
merged = _do_merge(results, spec)     # UNION / LEFT_JOIN / FIRST_ONLY
merge_cap_applied = False
cap = self._max_result_rows
if len(merged) > cap:
    merged = merged[:cap]
    merge_cap_applied = True
return merged, merge_cap_applied
```
- Bounds what the Orchestrator/LLM sees — critical for UNION strategy where N×cap rows collapse
- `ExecutionResult.merge_row_cap_applied: bool` field added to signal this

**When Stage 2 fires**: Only when UNION of multiple sub-queries each hitting their own cap would still produce > MAX_RESULT_ROWS combined rows.

---

## Pattern 3: PriorityErrorClassifier

**Addresses**: Error classification (8 types, Q3=B from NFR requirements)

**Problem**: Storing `error_type = "unknown"` on every failure forces CorrectionEngine to parse raw error strings — coupling U1 to MCP Toolbox error formats.

**Solution**: Classify inside U2 using a priority-ordered decision tree over exception type, HTTP status code, and error body keywords:

```
Priority order (first match wins):
  1. asyncio.TimeoutError                       → "timeout"
  2. aiohttp.ClientConnectionError              → "connection_error"
  3. HTTP status == 429                         → "rate_limit"
  4. HTTP status in (401, 403)                  → "auth_error"
  5. body contains table/column not found kws   → "schema_error"
  6. body contains cast/type mismatch kws       → "data_type_error"
  7. any HTTP error or body error present       → "query_error"
  8. (fallback)                                 → "unknown"
```

**Schema error keywords**: `"table not found"`, `"no such table"`, `"column not found"`, `"undefined column"`, `"relation does not exist"`, `"unknown collection"`

**Data type error keywords**: `"cast"`, `"type mismatch"`, `"invalid input syntax"`, `"conversion failed"`, `"cannot cast"`, `"invalid cast"`

**Implementation**: Single `_classify_error(exc, status, body) -> str` function in `mcp_client.py`, called by each connector's error handler. Centralised so keyword lists are maintained in one place.

---

## Pattern 4: StructuredObservabilityEmitter

**Addresses**: OBS-U2-01 through OBS-U2-05

**Problem**: Ad-hoc `print()` or unstructured logging makes it impossible to grep for specific sub-query IDs or correlate execution time across a multi-DB plan.

**Solution**: Every significant event emits a structured log line via the standard `logging` module with consistent keys:

```python
# Sub-query completion (success)
logger.info(
    "sub_query_complete",
    extra={
        "sub_query_id": result.sub_query_id,
        "db_type": result.db_type,
        "row_count": result.row_count,
        "execution_time_ms": result.execution_time_ms,
        "row_cap_applied": result.row_cap_applied,
    }
)

# Sub-query failure
logger.warning(
    "sub_query_failed",
    extra={
        "sub_query_id": result.sub_query_id,
        "db_type": result.db_type,
        "error_type": failure.error_type,
        "error_message": failure.error_message[:200],
    }
)

# Join key rewrite (debug)
logger.debug(
    "join_key_rewritten",
    extra={"sub_query_id": sq.id, "db_type": sq.db_type, "join_key": sq.join_key}
)
```

No result row *content* is ever logged (SEC-U2-04). Row counts and timing are safe.
