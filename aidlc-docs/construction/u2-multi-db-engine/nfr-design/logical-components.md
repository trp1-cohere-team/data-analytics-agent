# Logical Components
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11

---

## Component Map

```
agent/execution/
  engine.py
    MultiDBEngine          ← top-level; owns session; async context manager
      AsyncEngineLifecycle ← __aenter__/__aexit__ + MCPHealthProbe
      QueryRouter          ← dispatches SubQuery to correct connector
      PostgreSQLConnector  ← MCP tool: postgres_query
      SQLiteConnector      ← MCP tool: sqlite_query
      MongoDBConnector     ← MCP tool: mongodb_aggregate
      DuckDBConnector      ← MCP tool: duckdb_query
      JoinKeyResolver      ← pre-exec SQL rewrite + post-result row transform
      ResultMerger         ← UNION / LEFT_JOIN / FIRST_ONLY + stage-2 row cap
      RowCapGuard          ← stage-1 truncation (per-connector)
      ObservabilityEmitter ← structured log helper
  mcp_client.py
    MCPClient (Protocol)   ← injectable interface (mirrors U5 pattern)
    AiohttpMCPClient       ← production implementation
    ErrorClassifier        ← 8-type priority decision tree
    MCPHealthProbe         ← lightweight GET /healthz check
```

---

## Component Interfaces

### MultiDBEngine

```python
class MultiDBEngine:
    def __init__(self, mcp_toolbox_url: str, max_result_rows: int = 1000) -> None: ...
    async def __aenter__(self) -> "MultiDBEngine": ...   # creates session + health check
    async def __aexit__(self, *args: Any) -> None: ...   # closes session
    async def execute_plan(self, plan: QueryPlan) -> ExecutionResult: ...
```

**Invariants**:
- `execute_plan` must only be called inside `async with MultiDBEngine(...)` block
- If called outside, `self._session` is `None` → raises `RuntimeError`

---

### MCPClient (Protocol — injectable)

```python
class MCPClient(Protocol):
    async def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def health_check(self, timeout: float = 3.0) -> bool: ...
```

**AiohttpMCPClient** implements this protocol using the engine's shared `aiohttp.ClientSession`.

---

### MCPHealthProbe

```python
async def probe(session: aiohttp.ClientSession, base_url: str, timeout: float = 3.0) -> None:
    """Raises RuntimeError if MCP Toolbox is unreachable or returns 5xx."""
```

- Calls `GET {base_url}/healthz`
- HTTP 404 → pass (endpoint absent but server alive)
- HTTP 5xx → raise RuntimeError
- `aiohttp.ClientConnectionError` → raise RuntimeError
- `asyncio.TimeoutError` → raise RuntimeError

---

### ErrorClassifier

```python
def classify_error(
    exc: BaseException | None,
    http_status: int | None,
    body: str,
) -> str:
    """Returns one of 8 error type strings. Never raises."""
```

Priority order (first match wins):
1. `isinstance(exc, asyncio.TimeoutError)` → `"timeout"`
2. `isinstance(exc, aiohttp.ClientConnectionError)` → `"connection_error"`
3. `http_status == 429` → `"rate_limit"`
4. `http_status in (401, 403)` → `"auth_error"`
5. Schema keywords in `body.lower()` → `"schema_error"`
6. Type/cast keywords in `body.lower()` → `"data_type_error"`
7. `http_status` or `body` present → `"query_error"`
8. fallback → `"unknown"`

---

### RowCapGuard

**Stage 1** — embedded in each DB connector:
```python
def apply_per_subquery_cap(rows: list[dict], cap: int) -> tuple[list[dict], bool]:
    if len(rows) > cap:
        return rows[:cap], True     # (truncated_rows, row_cap_applied)
    return rows, False
```

**Stage 2** — embedded in ResultMerger:
```python
def apply_merge_cap(merged: list[dict], cap: int) -> tuple[list[dict], bool]:
    if len(merged) > cap:
        return merged[:cap], True   # (truncated_merged, merge_row_cap_applied)
    return merged, False
```

Both stages log a `logger.warning` when they fire (OBS-U2-04).

---

### JoinKeyResolver

Internal to `engine.py`. Two methods, both mutate in-place, neither raises:

```python
def pre_execute_resolve(self, plan: QueryPlan) -> None:
    """Rewrites SubQuery.query for SQL-based DBs with join key transform expressions."""

def post_result_resolve(self, results: list[SubQueryResult], plan: QueryPlan) -> None:
    """Applies transform_key to MongoDB result rows' join key columns."""
```

Delegates to U5: `detect_format`, `build_transform_expression`, `transform_key`.

---

### ResultMerger

```python
def merge(
    self,
    results: list[SubQueryResult],
    spec: MergeSpec,
) -> tuple[list[dict[str, Any]], bool]:
    """Returns (merged_rows, merge_row_cap_applied)."""
```

| Strategy | Logic |
|---|---|
| `UNION` | `extend` all non-failed `result.rows` → apply stage-2 cap |
| `LEFT_JOIN` | left side preserved; right rows matched by `spec.join_key`; unmatched → `{}` fill → cap |
| `FIRST_ONLY` | first non-failed non-empty result wins; no cap needed (already bounded by stage-1) |

---

### ObservabilityEmitter

Thin wrapper around `logging.getLogger("agent.execution")`. Provides three methods:

```python
def emit_complete(result: SubQueryResult) -> None: ...   # INFO
def emit_failure(result: SubQueryResult, failure: ExecutionFailure) -> None: ...  # WARNING
def emit_join_rewrite(sq: SubQuery) -> None: ...         # DEBUG
def emit_row_cap(sq_id: str, original_count: int, capped_at: int) -> None: ...   # WARNING
```

Never logs row content — only counts, IDs, types, and timings (SEC-U2-03, SEC-U2-04).

---

## models.py Additions Required

Two new fields on existing models (added in U2 code generation):

```python
class SubQueryResult(BaseModel):
    # ... existing fields ...
    row_cap_applied: bool = False          # Stage-1 cap fired

class ExecutionResult(BaseModel):
    # ... existing fields ...
    merge_row_cap_applied: bool = False    # Stage-2 cap fired
```

---

## Dependency Graph

```
MultiDBEngine
  ├── AsyncEngineLifecycle
  │     └── MCPHealthProbe ──────────────→ AiohttpMCPClient
  ├── QueryRouter
  │     ├── PostgreSQLConnector ──────────→ AiohttpMCPClient + RowCapGuard(stage-1)
  │     ├── SQLiteConnector ─────────────→ AiohttpMCPClient + RowCapGuard(stage-1)
  │     ├── MongoDBConnector ────────────→ AiohttpMCPClient + RowCapGuard(stage-1)
  │     └── DuckDBConnector ─────────────→ AiohttpMCPClient + RowCapGuard(stage-1)
  ├── JoinKeyResolver ─────────────────────→ U5: detect_format
  │                                              build_transform_expression
  │                                              transform_key
  ├── ResultMerger ────────────────────────→ RowCapGuard(stage-2)
  └── ObservabilityEmitter ────────────────→ logging.getLogger

AiohttpMCPClient
  └── ErrorClassifier
```
