# NFR Requirements
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API  
**Answers applied**: Q1=C, Q2=B, Q3=A, Q4=C, Q5=A, Q6=C, Q7=B, Q8=B, Q9=A, Q10=C, Q11=A, Q12=A

---

## Performance Requirements

### NFR-U1-P1: Query End-to-End Latency
- **Target**: p95 < 30 seconds for `POST /query` (Q1=C)
- **Rationale**: Complex multi-iteration ReAct loops may require several LLM calls and multiple DB sub-queries. 30s is the practical ceiling for a data analytics query with correction retries.
- **Scope**: Measured from request received to response sent, including all LLM calls, DB queries, and corrections.
- **Degraded path**: Requests that exceed 30s are NOT terminated; they complete and log `elapsed_ms` in structured output.

### NFR-U1-P2: Concurrent Request Throughput
- **Target**: 5–20 concurrent requests without queueing (Q2=B)
- **Rationale**: Small team usage pattern; concurrent requests are rare but possible.
- **Implementation**: `asyncio` event loop with `uvicorn` handles concurrency natively. No thread pool required.
- **Rate limit**: `POST /query` is hard-capped at 20 req/min via `slowapi` (config: `RATE_LIMIT="20/minute"`).

---

## Reliability Requirements

### NFR-U1-R1: LLM API Unavailability Handling
- **Behavior**: If OpenRouter LLM API is completely unavailable (connection refused, timeout, non-rate-limit error): return HTTP 503 immediately (Q3=A).
- **No retry on hard failure**: The 3-retry exponential backoff applies only to `RateLimitError` (429). Other errors → HTTP 503 immediately.
- **Response body**: `{"error": "llm_unavailable", "message": "LLM service is temporarily unavailable"}`

### NFR-U1-R2: MCP Toolbox (DB) Unavailability
- **Behavior**: Attempt the query; if all sub-queries fail, return structured error in the response body with HTTP 200 (Q4=C).
- **Answer field**: `"Database queries failed — no results available."`
- **Confidence**: 0.0
- **query_trace**: included (shows the failed query_database action and observation)
- **No HTTP 503**: DB failures are business-observable (partial results may succeed), not infrastructure failures.

### NFR-U1-R3: CorrectionExhausted Handling
- When `CorrectionEngine` exhausts all 3 attempts, the Orchestrator records the final failure as an observation and continues the ReAct loop (next `think()` step).
- If the loop terminates without `FINAL_ANSWER` due to repeated correction failures → BR-U1-03 applies (confidence=0.0 "could not answer" response).

---

## Security Requirements

### NFR-U1-S1: No Authentication Required
- The API is localhost-only / internal network deployment (Q5=A).
- No Bearer token, OAuth2, or API key authentication on inbound endpoints.
- OpenRouter API key is loaded from environment (`OPENROUTER_API_KEY`) — never passed through API responses.

### NFR-U1-S2: API Key Startup Validation
- If `OPENROUTER_API_KEY` is missing or empty at startup: log a WARNING but allow server to start (Q6=C).
- First LLM call will fail with a clear error; this is caught and returned as HTTP 503.
- **Rationale**: Allows the server to serve `/health` and `/schema` even without a valid LLM key.

### NFR-U1-S3: Content Security in Logs (SEC-U1-01)
- Query text (`question`), final answer, and intermediate observations are NEVER logged (Q8=B).
- Structured log fields for each request: `session_id`, `iterations_used`, `confidence`, `elapsed_ms`, `correction_count`, `action_sequence` (Q7=B).
- `action_sequence`: list of action names only, e.g. `["query_database", "search_kb", "FINAL_ANSWER"]`.
- No PII, no query content, no DB row data in any log at any level.

### NFR-U1-S4: Error Response Sanitization
- Global error handler middleware catches all unhandled exceptions.
- Response: HTTP 500 `{"error": "query_failed", "message": "<exception_type_name_only>"}`.
- Stack traces, file paths, and internal module names never appear in responses.

### NFR-U1-S5: Security Headers (SEC-U1-02)
- All responses include: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'none'`.
- Applied as ASGI middleware — not per-route.

---

## Observability Requirements

### NFR-U1-O1: Structured Request Logging
Per-request structured log entry (at completion of each `/query`):
```json
{
  "session_id": "...",
  "iterations_used": 3,
  "confidence": 0.85,
  "elapsed_ms": 4231.5,
  "correction_count": 1,
  "action_sequence": ["query_database", "search_kb", "FINAL_ANSWER"]
}
```
No question text, no answer content, no DB row data.

### NFR-U1-O2: Orchestrator Step Logging
Each `think()` and `act()` step logs at DEBUG level:
- `{"event": "think_step", "session_id": "...", "iteration": N, "action": "query_database"}`
- `{"event": "act_step", "session_id": "...", "iteration": N, "success": true, "elapsed_ms": 123.4}`
No reasoning text, no action_input content, no observation result content.

---

## Maintainability Requirements

### NFR-U1-M1: Testing — Orchestrator (Q11=A)
- Unit tests with mocked LLM client injected via `__init__` (Q10=C: DI pattern).
- Mock returns controlled `Thought` JSON sequences.
- Tests cover: normal termination, max_iterations reached, LLM parse error, correction loop.

### NFR-U1-M2: Testing — CorrectionEngine (Q12=A)
- Unit tests for each of the 5 fix strategy functions.
- PBT invariant: `classify_failure()` always returns a valid `FailureType` for any error string.
- Coverage target: all 5 FailureType branches exercised.

### NFR-U1-M3: Testing — AgentAPI
- Unit tests for request validation (422 paths), session_id handling, rate limit response.
- Integration test: full end-to-end `/query` with mocked Orchestrator.

### NFR-U1-M4: Testing — ContextManager
- Unit tests for Layer 1 cache, Layer 2 mtime refresh trigger, Layer 3 fresh load.
- Mocked file system and SchemaIntrospector.
