# Functional Design Plan — U3 Runtime Layer

## Unit Context
- **Unit**: U3 — Runtime Layer
- **Purpose**: Persistent memory, tool policy enforcement, and orchestration spine (conductor)
- **Modules**: `memory.py`, `tooling.py`, `conductor.py`
- **Dependencies**: U1 (all), U2 (all)

## Plan Steps
- [x] Step 1: Define memory.py business logic (3-layer file-based memory)
- [x] Step 2: Define tooling.py business logic (ToolRegistry + ToolPolicy)
- [x] Step 3: Define conductor.py business logic (session lifecycle + self-correction loop)
- [x] Step 4: Identify PBT-01 testable properties
- [x] Step 5: Generate functional design artifacts

## Questions Assessment
**No clarification questions required.** FR-04, FR-05, SEC-05, SEC-11, and the unit-of-work dependency map fully specify all module interfaces.
