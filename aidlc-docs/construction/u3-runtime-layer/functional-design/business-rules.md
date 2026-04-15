# Business Rules — U3 Runtime Layer

---

## BR-U3-01: Memory Lazy Initialization
**Rule**: Memory subsystem MUST NOT create files or directories at import or __init__. File system operations happen only on first write (save_turn, save_topic).
- **Enforcement**: BR-01 (zero side effects), FR-05

## BR-U3-02: Memory Caps
**Rule**: Session memory capped at `AGENT_MEMORY_SESSION_ITEMS` (12) turns. Topic memory capped at `AGENT_MEMORY_TOPIC_CHARS` (2500) chars. Exceeding caps triggers trimming, not errors.
- Session: oldest turns trimmed
- Topic: content truncated to char limit
- **Enforcement**: NFR-06

## BR-U3-03: Mutation Blocking
**Rule**: `ToolPolicy` MUST block SQL containing INSERT, UPDATE, DELETE, DROP, CREATE, ALTER before any tool invocation. Blocking is case-insensitive with word-boundary matching to avoid false positives (e.g., "CREATED_AT" should NOT be blocked).
- This is a defense-in-depth layer; backends also enforce read-only
- **Enforcement**: SEC-05, SEC-11

## BR-U3-04: Self-Correction Retry Cap
**Rule**: The self-correction loop MUST NOT exceed `AGENT_SELF_CORRECTION_RETRIES` (default 3). After exhausting retries, the conductor returns the best available answer with low confidence.
- Every retry MUST emit a trace event with `retry_count` field
- Every retry MUST write a CorrectionEntry to the corrections log
- **Enforcement**: FR-04, NFR-03

## BR-U3-05: Execution Step Cap
**Rule**: The main execution loop MUST NOT exceed `AGENT_MAX_EXECUTION_STEPS` (6). This prevents runaway agent loops.
- **Enforcement**: NFR-03

## BR-U3-06: Input Validation at System Boundary
**Rule**: `conductor.run()` validates all inputs at the system boundary:
- `question`: must be str, max 4096 chars
- `db_hints`: must be list of str, max 10 items
- Invalid inputs → return AgentResult with error answer, confidence=0.0
- **Enforcement**: SEC-05

## BR-U3-07: Global Error Handler
**Rule**: The conductor MUST have a global try/except wrapping the entire `run()` method. Unhandled exceptions MUST NOT propagate to callers. Instead, return a safe AgentResult with generic error message (no stack traces, no internal details).
- **Enforcement**: SEC-09, SEC-15

## BR-U3-08: Event Emission Completeness
**Rule**: The conductor MUST emit trace events for:
- `session_start` (at run begin)
- `tool_call` (before each invocation)
- `tool_result` (after each invocation, with outcome)
- `correction` (each retry attempt, with diagnosis + retry_count)
- `session_end` (at run end, with summary)
- DuckDB bridge events include `backend: "duckdb_bridge"`
- **Enforcement**: FR-06

## BR-U3-09: No Direct DuckDB Bridge Import
**Rule**: No U3 module imports `DuckDBBridgeClient` or `duckdb_bridge_client.py`. All DB access goes through `MCPClient` from `mcp_toolbox_client.py`.
- **Enforcement**: unit-of-work-dependency.md import rules

---

## Testable Properties (PBT-01)

### Invariant Properties (PBT-03)
| Component | Invariant |
|---|---|
| `ToolPolicy.validate_invocation()` | Mutation keywords always blocked; non-mutation queries always pass |
| Memory session cap | `len(turns) <= AGENT_MEMORY_SESSION_ITEMS` after any save_turn |
| Memory topic cap | `len(content) <= AGENT_MEMORY_TOPIC_CHARS` after any save_topic |
| Conductor retry count | `failure_count <= AGENT_SELF_CORRECTION_RETRIES` in returned AgentResult |

---

## Security Compliance Summary (U3 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| SECURITY-03 | Compliant | All modules use logging; conductor logs all phases |
| SECURITY-05 | Compliant | Input validation at conductor boundary; ToolPolicy validates payloads |
| SECURITY-09 | Compliant | Global error handler returns generic messages; no stack traces to callers |
| SECURITY-11 | Compliant | ToolPolicy is isolated security-critical module; defense-in-depth |
| SECURITY-13 | Compliant | Memory JSONL parsing with try/except; no pickle/eval |
| SECURITY-15 | Compliant | Global error handler; all external calls have try/except; resource cleanup |

## PBT Compliance Summary (U3 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| PBT-01 | Compliant | 4 invariant properties identified |
| PBT-03 | Compliant (design) | Mutation blocking, memory caps, retry cap invariants documented |
