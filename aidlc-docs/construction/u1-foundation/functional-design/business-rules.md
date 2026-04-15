# Business Rules — U1 Foundation

## Overview
Business rules for the foundation layer focus on configuration safety, event integrity, and data validation. These are the invariants that all downstream units depend on.

---

## BR-01: Zero Side Effects on Import
**Rule**: Importing `types.py`, `config.py`, or any utility module MUST NOT trigger network calls, file writes, or resource allocation.
- `config.py` reads env vars at import time (fast, no I/O beyond `os.environ`)
- `events.py` does NOT open the event file at import — only on first `emit_event()` call
- `types.py` contains only dataclass definitions
- **Enforcement**: SEC-09 (security hardening — minimal initialization)

---

## BR-02: Offline Mode Completeness
**Rule**: When `AGENT_OFFLINE_MODE=1`, every module that would make an external call MUST use stub data from `config.py` instead.
- LLM calls: `OFFLINE_LLM_RESPONSE`
- MCP tool discovery: `OFFLINE_TOOL_LIST` (all 4 tools)
- MCP tool invocation: `OFFLINE_INVOKE_RESULTS` (keyed by db_type)
- DuckDB bridge: same `OFFLINE_INVOKE_RESULTS["duckdb"]`
- **Zero HTTP calls permitted** when offline mode is active
- **Enforcement**: NFR-01

---

## BR-03: Configuration Safety
**Rule**: No secret or sensitive value may have a non-empty default that points to a live service.
- `OPENROUTER_API_KEY` defaults to `""` (requires explicit setting)
- `DUCKDB_BRIDGE_URL` defaults to `""` (no default live server per SEC-09)
- `MCP_TOOLBOX_URL` defaults to `"http://localhost:5000"` (local only, acceptable)
- No model name hardcoded in source — always read from `OPENROUTER_MODEL` env var (FR-13)
- **Enforcement**: NFR-04, SEC-09

---

## BR-04: Event Integrity
**Rule**: Every event written to the ledger MUST be valid and parseable.
- Events are validated before write: `event_type`, `session_id`, `timestamp` must be non-empty strings
- JSON serialization uses `json.dumps()` — no `pickle` or `eval` (SEC-13)
- Malformed events are rejected with a logged warning, not silently dropped
- File handle always closed via `with` statement (SEC-15)
- **Enforcement**: FR-06, SEC-13, SEC-15

---

## BR-05: Dataclass Type Constraints
**Rule**: Domain entity fields with constrained domains MUST enforce their constraints.

| Entity | Field | Constraint |
|---|---|---|
| `AgentResult` | `confidence` | Must be in [0.0, 1.0] |
| `AgentResult` | `failure_count` | Must be >= 0 |
| `ExecutionStep` | `status` | Must be in `{"pending", "success", "failed", "corrected"}` |
| `FailureDiagnosis` | `category` | Must be in `{"query", "join-key", "db-type", "data-quality"}` |
| `MemoryTurn` | `role` | Must be in `{"user", "assistant"}` |
| `ContextPacket` | all layers | Must be `str` type (empty string allowed) |

- **Enforcement via**: `__post_init__` validation on dataclasses
- **PBT coverage**: PBT-03 invariant tests verify these constraints hold across generated inputs

---

## BR-06: Text Utility Invariants
**Rule**: Text processing functions MUST satisfy mathematical invariants.
- `score_overlap(keywords, doc)` always in [0.0, 1.0]
- `score_overlap([], doc)` == 0.0 (empty keywords = zero score)
- `extract_keywords(text)` returns deduplicated list; len(result) <= token count of input
- `filename_stem_overlap(keywords, filename)` always in [0.0, 1.0]
- `freshness_bonus(path)` always in [0.0, 0.3]
- **Enforcement**: PBT-03 invariant tests

---

## BR-07: Logging Safety (SEC-03)
**Rule**: The logging configuration established in `config.py` MUST be used by all modules.
- All modules use `logging.getLogger(__name__)` — no `print()` for production output
- Log format includes: timestamp, log level, module name, session_id
- Sensitive data NEVER logged: API keys, DB connection strings, full SQL queries at INFO+
- SQL logged at DEBUG only; at INFO+ use `sanitize_sql_for_log()` from `db_utils.py`

---

## BR-08: Error Path Safety (SEC-15)
**Rule**: All file I/O operations in U1 MUST have explicit error handling.
- `emit_event()`: catches `OSError`/`IOError`, logs warning, does not crash the agent
- `read_events()`: catches `json.JSONDecodeError` per line, skips malformed, logs warning
- `freshness_bonus()`: catches `FileNotFoundError`, returns 0.0
- All file handles released in error paths (context managers)

---

## Testable Properties (PBT-01)

### Round-Trip Properties (PBT-02)
| Component | Property | Test Shape |
|---|---|---|
| `TraceEvent.to_dict()` / `from_dict()` | Serialize then deserialize = original | `TraceEvent.from_dict(e.to_dict()) == e` |
| `ContextPacket.to_dict()` / `from_dict()` | Serialize then deserialize = original | `ContextPacket.from_dict(cp.to_dict()) == cp` |
| Event JSONL write / read | Write event, read back, equals original | `read_events(path)[-1] == original_event` |

### Invariant Properties (PBT-03)
| Component | Invariant | Test Shape |
|---|---|---|
| `FailureDiagnosis.category` | Always one of 4 valid categories | `category in {"query","join-key","db-type","data-quality"}` |
| `score_overlap()` | Result always in [0.0, 1.0] | `0.0 <= score_overlap(kw, doc) <= 1.0` |
| `AgentResult.confidence` | Always in [0.0, 1.0] | `0.0 <= result.confidence <= 1.0` |
| `extract_keywords()` | Output is subset of input tokens | `all(kw in tokens for kw in extract_keywords(text))` |

---

## Security Compliance Summary (U1 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| SECURITY-03 | Compliant | Logging framework configured in config.py; format includes timestamp, session_id, level |
| SECURITY-05 | N/A | No API endpoints in U1 |
| SECURITY-09 | Compliant | No default credentials; DUCKDB_BRIDGE_URL defaults empty; generic errors |
| SECURITY-10 | N/A | requirements.txt is in U5 |
| SECURITY-11 | N/A | U1 is foundation types/config, not application design |
| SECURITY-13 | Compliant | JSON parsing via json.loads() with try/except; no pickle/eval |
| SECURITY-15 | Compliant | All file I/O has explicit error handling; resource cleanup via context managers |

## PBT Compliance Summary (U1 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| PBT-01 | Compliant | Testable properties identified above (3 round-trip + 4 invariant) |
| PBT-02 | Compliant (design) | Round-trip properties documented for TraceEvent, ContextPacket, Event JSONL |
| PBT-03 | Compliant (design) | Invariant properties documented for FailureDiagnosis, score_overlap, confidence |
| PBT-07 | N/A | Generator quality verified during code generation |
| PBT-08 | N/A | Shrinking/reproducibility verified during code generation |
| PBT-09 | N/A | Framework selection (Hypothesis) already decided in requirements |
