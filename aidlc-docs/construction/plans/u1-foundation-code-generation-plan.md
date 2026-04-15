# Code Generation Plan — U1 Foundation

## Unit Context
- **Unit**: U1 — Foundation
- **Purpose**: Zero-dependency base layer; all other units import from this one
- **Functional Design**: `aidlc-docs/construction/u1-foundation/functional-design/`
- **Dependencies**: None
- **Workspace Root**: `/home/nurye/Desktop/TRP1/week8/OracleForge`

## Code Location
- Application code: workspace root (per greenfield monolith pattern)
- Module paths: `agent/data_agent/`, `agent/runtime/`, `utils/`
- Documentation: `aidlc-docs/construction/u1-foundation/code/`

## Requirement Traceability
| Step | Requirement(s) | Module |
|---|---|---|
| Step 1 | — | Project structure + `__init__.py` files |
| Step 2 | FR-01, FR-02, FR-04, FR-05, FR-06, FR-12 | `agent/data_agent/types.py` |
| Step 3 | NFR-01, NFR-04, SEC-03, SEC-09, FR-13 | `agent/data_agent/config.py` |
| Step 4 | FR-06, SEC-13, SEC-15 | `agent/runtime/events.py` |
| Step 5 | FR-09 | `utils/text_utils.py` |
| Step 6 | FR-06 | `utils/trace_utils.py` |
| Step 7 | FR-03, SEC-03 | `utils/db_utils.py` |

---

## Plan Steps

- [x] **Step 1: Project Structure Setup**
  - Create directory tree: `agent/data_agent/`, `agent/runtime/`, `utils/`, `tests/`, `eval/`, `kb/`, `sandbox/`, `probes/`, `results/`
  - Create `__init__.py` for all Python packages: `agent/`, `agent/data_agent/`, `agent/runtime/`, `utils/`, `tests/`
  - Verify no existing files are overwritten

- [x] **Step 2: Generate `agent/data_agent/types.py`**
  - 10 dataclasses: `AgentResult`, `TraceEvent`, `ContextPacket`, `ExecutionStep`, `CorrectionEntry`, `LayerContent`, `FailureDiagnosis`, `ToolDescriptor`, `InvokeResult`, `MemoryTurn`
  - `__post_init__` validation for constrained fields (BR-05)
  - `to_dict()` / `from_dict()` serialization on `TraceEvent` and `ContextPacket` (PBT-02 round-trip)
  - Backward-compat property aliases on `ContextPacket` (FR-02)
  - Zero side effects on import (BR-01)

- [x] **Step 3: Generate `agent/data_agent/config.py`**
  - All env-driven constants from business-logic-model.md
  - Offline stubs: `OFFLINE_LLM_RESPONSE`, `OFFLINE_TOOL_LIST`, `OFFLINE_INVOKE_RESULTS`
  - Logging configuration setup (SEC-03)
  - No hardcoded secrets (NFR-04, SEC-09)
  - `DUCKDB_BRIDGE_URL` defaults to empty string (SEC-09)

- [x] **Step 4: Generate `agent/runtime/events.py`**
  - `emit_event(event: TraceEvent)` — JSONL append with lazy file creation
  - `read_events(path: str) -> list[TraceEvent]` — parse with error handling
  - JSON validation before write (SEC-13)
  - Resource cleanup via context managers (SEC-15)
  - Safe fallback on I/O errors (SEC-15)

- [x] **Step 5: Generate `utils/text_utils.py`**
  - `extract_keywords()`, `score_overlap()`, `filename_stem_overlap()`, `freshness_bonus()`
  - All return values bounded in documented ranges (BR-06)
  - FileNotFoundError handling in `freshness_bonus()` (SEC-15)

- [x] **Step 6: Generate `utils/trace_utils.py`**
  - `build_trace_event()` — factory with defaults
  - `format_trace_summary()` — human-readable formatter

- [x] **Step 7: Generate `utils/db_utils.py`**
  - `db_type_from_kind()` — kind → db_type mapping
  - `validate_db_url()` — basic format validation
  - `sanitize_sql_for_log()` — SQL redaction for safe logging (SEC-03)

- [x] **Step 8: Generate code summary documentation**
  - `aidlc-docs/construction/u1-foundation/code/code-summary.md`

## Total Steps: 8
## Estimated Scope: 6 Python source files + __init__.py files + 1 doc
