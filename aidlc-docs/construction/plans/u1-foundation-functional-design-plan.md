# Functional Design Plan — U1 Foundation

## Unit Context
- **Unit**: U1 — Foundation
- **Purpose**: Zero-dependency base layer. All other units import from this one.
- **Modules**: `types.py`, `config.py`, `events.py`, `text_utils.py`, `trace_utils.py`, `db_utils.py`
- **Dependencies**: None (foundation layer)

## Plan Steps

- [x] Step 1: Define all shared domain entities in `types.py` (10 dataclasses)
- [x] Step 2: Define config system business rules (`config.py` — env-driven settings, offline stubs)
- [x] Step 3: Define event ledger business logic (`events.py` — JSONL append, validation)
- [x] Step 4: Define text utility algorithms (`text_utils.py` — keyword extraction, scoring)
- [x] Step 5: Define trace utility business logic (`trace_utils.py` — event builders)
- [x] Step 6: Define DB utility business logic (`db_utils.py` — connection helpers)
- [x] Step 7: Identify PBT-01 testable properties for U1 components
- [x] Step 8: Generate functional design artifacts

## Questions Assessment
**No clarification questions required.** The approved requirements (FR-01, FR-02, FR-06, FR-12, NFR-01 through NFR-06, SEC-03/09/13/15) fully specify:
- All dataclass field names and types
- All environment variables with defaults
- Event JSONL schema
- Offline stub behavior
- KB retrieval algorithm components
