# Business Rules
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## BR-U1-01: Request Validation

| Field | Rule |
|---|---|
| `question` | 1 ≤ len ≤ 4096 characters; empty string rejected (HTTP 422) |
| `databases` | Optional; if provided, must be a list of strings; empty list treated as None (no restriction) |
| `session_id` | Optional; if provided, used as-is without validation (Q11=B); if absent, server generates UUID4 |

---

## BR-U1-02: Session ID Policy

- Caller-supplied `session_id` is accepted and used unchanged (Q11=B)
- This enables client-side session continuity (e.g., follow-up questions)
- Server never validates whether the `session_id` matches an existing session in KnowledgeBase or MemoryManager
- A new server-generated UUID4 is created only when `session_id` is absent in the request

---

## BR-U1-03: ReAct Iteration Limit

- Maximum iterations per `run()` call: `settings.max_react_iterations` (default 10)
- If `FINAL_ANSWER` is produced at or before iteration 10 → normal termination
- If iteration 10 completes without `FINAL_ANSWER` → (Q2=C):
  - `answer = "I could not answer this question within the iteration limit."`
  - `confidence = 0.0`
  - `query_trace` includes all 10 iterations
  - HTTP 200 (not an error — it is a valid response)

---

## BR-U1-04: Confidence Threshold

- Confidence is LLM-reported (Q3=A): a float 0.0–1.0 in the `confidence` field of the JSON response
- The `confidence_threshold` setting (default 0.85) is used as an early-exit check:
  - If `thought.confidence >= settings.confidence_threshold` AND action is `FINAL_ANSWER` → terminate immediately
- The Orchestrator does NOT terminate early based on confidence alone — only on `FINAL_ANSWER` action

---

## BR-U1-05: LLM Response Format Contract

- The Orchestrator system prompt instructs the LLM to always return valid JSON (Q1=B):
  ```json
  {
    "reasoning": "<chain-of-thought>",
    "action": "<action_name>",
    "action_input": { ... },
    "confidence": 0.0
  }
  ```
- If the LLM returns malformed JSON: log a warning, treat as `action=FINAL_ANSWER` with `answer="Parse error"` and `confidence=0.0`
- The Orchestrator never uses function-calling format; tools are documented in the system prompt only

---

## BR-U1-06: query_database Action Format

- The LLM provides the full `QueryPlan` JSON as `action_input` for `query_database` actions (Q4=B)
- The Orchestrator deserializes `action_input` as `QueryPlan(**action_input)` before passing to `MultiDBEngine`
- If deserialization fails → treat as execution failure → pass to CorrectionEngine with `error_type="query_error"`

---

## BR-U1-07: Correction Attempt Limits

- Maximum correction attempts per query session: `settings.max_correction_attempts` (default 3)
- Attempt counter is per-session, not per-failure: if the first correction fails and the second fails, the third attempt uses `llm_corrector` regardless of failure type
- When `max_correction_attempts` is exceeded → raise `CorrectionExhausted` → Orchestrator records as observation with `success=False` → continues to next `think()` iteration
- Every correction attempt (success or failure) is appended to `KnowledgeBase.corrections` (Q5=B)

---

## BR-U1-08: CorrectionEngine Fix Strategy Priority

Order of fix strategies (cheapest to most expensive):

| Priority | Strategy | Trigger | LLM Call? |
|---|---|---|---|
| 1 | `rule_syntax` | SYNTAX_ERROR | No |
| 2 | `rule_join_key` | JOIN_KEY_MISMATCH | No |
| 3 | `rule_db_type` | WRONG_DB_TYPE | No |
| 4 | `rule_null_guard` | DATA_QUALITY | No |
| 5 | `llm_corrector` | UNKNOWN | Yes |

---

## BR-U1-09: fix_syntax_error Patterns (Q9=C)

The rule-based syntax fixer handles exactly these patterns (no others):

1. **Missing string quotes**: `WHERE name = value` → `WHERE name = 'value'`  
   Detection: bare word after `=` that is not a number, column ref, or subquery
2. **GROUP BY without aggregate**: `SELECT col, col2 GROUP BY col`  
   Fix: add `COUNT(*) AS count_` to the SELECT list
3. **Wrong dialect keyword — row limiting**:
   - `ROWNUM` → `LIMIT` (SQLite, Postgres, DuckDB)
   - `TOP N` → `LIMIT N` (SQLite, Postgres, DuckDB)
4. **Wrong dialect keyword — null handling**:
   - `ISNULL(col)` → `col IS NULL`
   - `NVL(col, val)` → `COALESCE(col, val)`

Any other syntax error pattern → escalates to `UNKNOWN` → `llm_corrector`

---

## BR-U1-10: fix_wrong_db_type Detection Rules (Q10=B)

Detection is by matching `error_message` against db_type-specific error signal patterns:

| Target DB | Error Signals |
|---|---|
| postgres | `"psycopg"`, `"pg_"`, `"relation does not exist"`, `"column ... does not exist"` |
| sqlite | `"no such table"`, `"no such column"`, `"sqlite3"` |
| mongodb | `"$match"`, `"aggregation error"`, `"bson"`, `"document"` |
| duckdb | `"catalog"`, `"binder error"`, `"duckdb"` |

If the error signals of DB-X appear in a query routed to DB-Y (DB-Y ≠ DB-X): reroute to DB-X.

---

## BR-U1-11: LLM Rate Limit Retry Policy

- Maximum retries on `RateLimitError`: 3 attempts
- Backoff schedule: 1s → 2s → 4s (exponential, base=2)
- After 3 failed attempts: propagate exception → Orchestrator treats as `Observation(success=False)`
- No retry on other errors (connection error, bad response, etc.)

---

## BR-U1-12: Layer 2 Cache Refresh (Q6=A)

- Background task runs every `settings.layer2_refresh_interval_s` seconds (default 60)
- Refresh check: compare `file.stat().st_mtime` for each `.md` file in KB subdirs against `self._layer2_loaded_at`
- If ANY file is newer → reload all domain documents (all-or-nothing reload)
- `CHANGELOG.md` files are excluded from serving to LLM (KB-09) but included in mtime scan

---

## BR-U1-13: Layer 3 Corrections Limit

- Layer 3 loads the most recent `settings.corrections_limit` entries (default 50)
- If `corrections.json` has more than 50 entries: load only the last 50 (by array position — most recent appended last)
- All 50 (or fewer) are formatted as Markdown bullets for the LLM prompt (Q7=B)

---

## BR-U1-14: Session Transcript Persistence (Q8=A)

- `AgentAPI.handle_query()` calls `MemoryManager.save_session()` **after** receiving `OrchestratorResult` and **before** returning the HTTP response
- The summary passed to `save_session()` is: `f"Q: {question[:200]} A: {str(answer)[:200]}"`
- If `save_session()` raises an exception: log the error; do NOT fail the HTTP request (best-effort persistence)

---

## BR-U1-15: Error Response Policy

- All unhandled exceptions are caught by the global error handler middleware
- Response: HTTP 500 `{"error": "query_failed", "message": "<safe message>"}`
- Safe message: the exception type name only; never include stack trace, query text, or internal paths
- FastAPI validation errors (422) are returned in the default Pydantic format

---

## BR-U1-16: Security Header Policy (Q12=B)

Middleware adds the following headers to every response:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `default-src 'none'` |

These headers are added as HTTP response middleware (not per-route). No `Strict-Transport-Security` (not a TLS terminating server in dev).

---

## BR-U1-17: Rate Limiting

- Rate limit on `POST /query`: `settings.rate_limit` (default `"20/minute"`) via `slowapi`
- Rate limit key: client IP address
- When rate limit exceeded: HTTP 429 `{"error": "rate_limit_exceeded"}`
- `GET /health` and `GET /schema` are not rate-limited
