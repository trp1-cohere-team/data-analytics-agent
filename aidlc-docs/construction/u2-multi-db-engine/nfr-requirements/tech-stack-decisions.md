# Tech Stack Decisions
# U2 — Multi-DB Execution Engine

**Date**: 2026-04-11

---

## Core Dependencies (All Pre-Selected — No New Packages Needed)

| Package | Version (pinned) | Role | Reason |
|---|---|---|---|
| `aiohttp` | 3.9.5 | MCP Toolbox HTTP client | Already in requirements.txt (U5 SchemaIntrospector); same library for consistency |
| `asyncio` | stdlib | Concurrency (gather, wait_for, timeout) | Standard library; no extra dependency |
| `pydantic` | 2.7.1 | Model validation (SubQuery, SubQueryResult, ExecutionResult) | Already in requirements.txt |
| `pydantic-settings` | 2.2.1 | `config.max_result_rows` setting | Already in requirements.txt |
| `python-dotenv` | 1.0.1 | `.env` loading | Already in requirements.txt |

**No new packages required for U2.** All dependencies were established in U5.

---

## Key Technical Decisions

### aiohttp Session: Per-Engine-Instance (Q2=C)

**Decision**: `MultiDBEngine` creates and owns one `aiohttp.ClientSession`. The engine implements the async context manager protocol.

**Why not A (per-request)**:
- Per-request sessions create and tear down a TCP connection pool on every `execute_plan` call
- Under load (many agent queries), this causes unnecessary connection churn

**Why not B (module-level singleton)**:
- Singleton sessions require careful application shutdown handling
- Can cause "Session is closed" errors if the event loop is recreated (e.g., in tests)
- Harder to mock in unit tests

**Why C**:
- Deterministic lifecycle tied to the engine instance
- `async with MultiDBEngine(...) as engine` is idiomatic asyncio
- Easy to inject a mock session in unit tests by passing a mock client

---

### Row Cap: Configurable via config.py (Q1=D)

**Decision**: `config.max_result_rows: int = 1000` controls the hard truncation limit.

**Implementation in `agent/config.py`**:
```python
max_result_rows: int = Field(default=1000, alias="MAX_RESULT_ROWS")
```

**Why not C (hardcoded 1000)**:
- Different deployment environments may need different limits
- Benchmark runs (U4) may need higher caps to avoid truncating ground-truth answers

**Why not A (no cap)**:
- MongoDB `$lookup` + DuckDB analytical queries can return 100K+ rows
- Feeding 100K rows to the LLM is beyond context window capacity

---

### Error Classification: 8-Type Taxonomy (Q3=B)

**Decision**: Parse both exception type and MCP Toolbox HTTP response body to assign one of 8 error types.

**Implementation approach**:
```python
def _classify_error(exc: BaseException | None, status: int | None, body: str) -> str:
    if isinstance(exc, asyncio.TimeoutError): return "timeout"
    if isinstance(exc, aiohttp.ClientConnectionError): return "connection_error"
    if status == 429: return "rate_limit"
    if status in (401, 403): return "auth_error"
    body_lower = body.lower()
    if any(kw in body_lower for kw in ("table not found","no such table","column not found","undefined column")):
        return "schema_error"
    if any(kw in body_lower for kw in ("cast","type mismatch","invalid input syntax","conversion failed")):
        return "data_type_error"
    if body or status: return "query_error"
    return "unknown"
```

**Why not A (4 types)**:
- CorrectionEngine (U1) needs `schema_error` to decide on re-routing vs. re-phrasing
- `data_type_error` maps to a distinct fix strategy (type cast rule)
- Richer taxonomy enables better automated correction without LLM overhead

**Why not C (simple + raw body)**:
- Pushing classification to CorrectionEngine creates coupling between U1 and MCP Toolbox error format
- Centralising in U2 means classification changes need only one file

---

## config.py Additions Required

Add to `agent/config.py` `Settings` class:

```python
max_result_rows: int = Field(default=1000, alias="MAX_RESULT_ROWS")
```

Add to `.env.example`:
```
MAX_RESULT_ROWS=1000
```

---

## Files to Generate

| File | Description |
|---|---|
| `agent/execution/engine.py` | `MultiDBEngine` class with all sub-components; async context manager |
| `agent/execution/mcp_client.py` | `AiohttpMCPClient` and `MCPClient` protocol (mirrors U5 pattern) |
| `tests/unit/test_execution_engine.py` | Unit tests for engine; mock MCPClient injected |
| `tests/unit/test_mcp_client.py` | Unit tests for MCPClient error classification |
