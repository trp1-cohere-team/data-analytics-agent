# NFR Requirements
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11  
**Design Decisions**: Q1=D (configurable row cap), Q2=C (per-engine session), Q3=B (8-type error classification)

---

## Performance Requirements

| ID | Requirement | Value | Source |
|---|---|---|---|
| PERF-U2-01 | Per-sub-query execution timeout | 30 seconds (`asyncio.wait_for`) | Architecture |
| PERF-U2-02 | Sub-query fan-out | All sub-queries run concurrently via `asyncio.gather` | Architecture |
| PERF-U2-03 | Result row cap per sub-query | `config.max_result_rows` (default 1000); hard truncate | Q1=D |
| PERF-U2-04 | Row cap flag | `SubQueryResult.row_cap_applied: bool = True` when truncated | Q1=D |
| PERF-U2-05 | Config key | `MAX_RESULT_ROWS: int = 1000` added to `agent/config.py` | Q1=D |

**Rationale**: Unbounded result sets from DuckDB analytical queries or MongoDB aggregations could exhaust agent memory. The configurable cap defaults to 1000 rows — sufficient for NL answer generation while protecting against runaway queries.

---

## Reliability Requirements

| ID | Requirement | Detail |
|---|---|---|
| REL-U2-01 | Partial failure continuation | A single sub-query failure does not abort the plan; others continue (Q2=B functional design) |
| REL-U2-02 | Exception containment | All exceptions inside `_execute_sub_query` are caught; none propagate to `execute_plan` caller |
| REL-U2-03 | JoinKeyResolver non-blocking | `join_key_unresolvable=True` flag on failure; sub-query executes unchanged |
| REL-U2-04 | Row-cap flag propagation | Caller is always informed of truncation via `row_cap_applied`; never silently drops rows |
| REL-U2-05 | Empty result contract | `SubQueryResult.rows` is always `list[dict]`; never `None` |

---

## Error Classification Requirements

8-type error taxonomy (Q3=B) — parsed from exception type and MCP Toolbox HTTP error body:

| Error Type | Classification Logic |
|---|---|
| `timeout` | `asyncio.TimeoutError` raised during `wait_for` |
| `connection_error` | `aiohttp.ClientConnectionError` or `aiohttp.ServerDisconnectedError` |
| `query_error` | MCP Toolbox returns HTTP 200 with `{"error": "..."}` in body, or HTTP 4xx with non-auth body |
| `auth_error` | HTTP 401 or 403 from MCP Toolbox |
| `schema_error` | Error body contains "table not found", "column not found", "no such table", "undefined column" |
| `data_type_error` | Error body contains "cast", "type mismatch", "invalid input syntax", "conversion failed" |
| `rate_limit` | HTTP 429 from MCP Toolbox |
| `unknown` | Any exception or error body not matching above patterns |

**Classification order**: The classifier checks in priority order — timeout → connection_error → rate_limit → auth_error → schema_error → data_type_error → query_error → unknown.

---

## Resource Management Requirements

| ID | Requirement | Detail |
|---|---|---|
| RES-U2-01 | Session strategy | Per-engine-instance `aiohttp.ClientSession` (Q2=C) |
| RES-U2-02 | Session creation | Created in `MultiDBEngine.__aenter__` (async context manager entry) |
| RES-U2-03 | Session closure | Closed in `MultiDBEngine.__aexit__` (async context manager exit) |
| RES-U2-04 | Async context manager | `MultiDBEngine` implements `__aenter__` / `__aexit__` |
| RES-U2-05 | Session sharing | One session shared across all 4 DB connectors within a single `execute_plan` call |
| RES-U2-06 | No cross-call sharing | Sessions are NOT shared across different `execute_plan` invocations (one engine instance → one concurrent request) |

**Usage pattern**:
```python
async with MultiDBEngine(mcp_toolbox_url=settings.mcp_toolbox_url) as engine:
    result = await engine.execute_plan(plan)
```

---

## Security Requirements

| ID | Requirement | Detail |
|---|---|---|
| SEC-U2-01 | MCP Toolbox URL from config only | `config.mcp_toolbox_url` — never accept URL from query input |
| SEC-U2-02 | No auth headers to MCP Toolbox | Localhost-only service; no API key sent |
| SEC-U2-03 | Query content not logged at DEBUG level | Sub-query SQL/pipeline may contain sensitive data; never log full query text |
| SEC-U2-04 | Row count logged, not row content | Observability logs include row counts and timing; never log result row data |

---

## Observability Requirements

| ID | Requirement | Detail |
|---|---|---|
| OBS-U2-01 | `execution_time_ms` per sub-query | Populated on success and failure (0.0 on instant error) |
| OBS-U2-02 | Log sub-query completion | `logger.info` with `sub_query_id`, `db_type`, `row_count`, `execution_time_ms` |
| OBS-U2-03 | Log failures | `logger.warning` with `sub_query_id`, `db_type`, `error_type`, `error_message[:200]` |
| OBS-U2-04 | Log row cap events | `logger.warning` when `row_cap_applied=True` with actual row count before truncation |
| OBS-U2-05 | Log join key rewrites | `logger.debug` when pre-execution rewrite applied to a SubQuery |
