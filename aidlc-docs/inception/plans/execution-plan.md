# Execution Plan — OracleForge Data Agent

## Detailed Analysis Summary

### Change Impact Assessment
- **User-facing changes**: Yes — `run_agent()` public API + DAB evaluation harness
- **Structural changes**: Yes — 20+ new modules across 4 layers
- **Data model changes**: Yes — `types.py`, event ledger schema, KB documents, memory schema
- **API changes**: Yes — Google MCP Toolbox contract + custom DuckDB bridge contract
- **NFR impact**: Yes — offline mode, timeout guards, retry cap, security constraints, PBT

### Risk Assessment
- **Risk Level**: High
- **Rollback Complexity**: Easy (greenfield — revert is full delete)
- **Testing Complexity**: Complex — unit tests, integration mocks, DAB smoke test, PBT

---

## Workflow Visualization

### Text Representation

```
INCEPTION PHASE
  [x] Workspace Detection     COMPLETED
  [-] Reverse Engineering     SKIPPED (greenfield)
  [x] Requirements Analysis   COMPLETED
  [-] User Stories            SKIPPED (Q7=B)
  [x] Workflow Planning       IN PROGRESS
  [-] Application Design      SKIPPED (Q10=B; arch pre-specified)
  [>] Units Generation        EXECUTE

CONSTRUCTION PHASE
  [>] Functional Design       EXECUTE (per-unit — complex business logic)
  [-] NFR Requirements        SKIPPED (tech stack + NFRs fully in requirements)
  [-] NFR Design              SKIPPED (NFR patterns captured in requirements)
  [-] Infrastructure Design   SKIPPED (no cloud infra; local file-based)
  [>] Code Generation         EXECUTE (per-unit, always)
  [>] Build and Test          EXECUTE (always)

OPERATIONS PHASE
  [ ] Operations              PLACEHOLDER
```

---

## Phases to Execute

### INCEPTION PHASE
- [x] Workspace Detection — COMPLETED
- [-] Reverse Engineering — SKIPPED (greenfield, no existing codebase)
- [x] Requirements Analysis — COMPLETED (including post-approval revision)
- [-] User Stories — SKIPPED (Q7=B; requirements sufficiently detailed)
- [x] Workflow Planning — IN PROGRESS
- [-] Application Design — SKIPPED (Q10=B; full module breakdown pre-specified)
- [>] Units Generation — EXECUTE
  - **Rationale**: 20+ modules across 5 functional layers need structured decomposition into parallel development units; unit artifacts needed to drive per-unit Construction loop

### CONSTRUCTION PHASE (Per-Unit Loop)
- [>] Functional Design — EXECUTE per unit
  - **Rationale**: Each unit has complex business logic (correction loop, context layering, memory management) that benefits from explicit data model and business rule design before code generation
- [-] NFR Requirements — SKIPPED
  - **Rationale**: Tech stack fully decided; all NFRs (timeouts, offline mode, retry caps) documented in requirements.md
- [-] NFR Design — SKIPPED
  - **Rationale**: NFR patterns (Hypothesis for PBT, structured logging, ToolPolicy for security) specified in requirements; no design stage needed
- [-] Infrastructure Design — SKIPPED
  - **Rationale**: No cloud infrastructure; local file-based memory, `.env` config, Docker Compose only for MCP/DB
- [>] Code Generation — EXECUTE per unit (always)
- [>] Build and Test — EXECUTE (always)

### OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

---

## Units of Work (Preview — will be detailed in Units Generation)

The system decomposes into **5 development units** ordered by dependency:

| Unit | Name | Modules | Depends On |
|---|---|---|---|
| U1 | Foundation | `types.py`, `config.py`, `events.py`, `utils/` | — |
| U2 | Data Layer | `context_layering.py`, `knowledge_base.py`, `failure_diagnostics.py`, `mcp_toolbox_client.py` | U1 |
| U3 | Runtime Layer | `memory.py`, `tooling.py`, `conductor.py` | U1, U2 |
| U4 | Agent + Sandbox | `oracle_forge_agent.py`, `execution_planner.py`, `result_synthesizer.py`, `sandbox_server.py`, `sandbox_client.py` | U1, U2, U3 |
| U5 | Eval + Supporting | `eval/`, `kb/`, `agent/AGENT.md`, `tools.yaml`, `probes/`, `README.md` | U1–U4 |

---

## Success Criteria
- **Primary Goal**: Production-grade data agent passing DAB smoke test (2 trials, bookreview + stockmarket)
- **Key Deliverables**: All modules from requirements.md directory structure; all tests passing; README with architecture diagram
- **Quality Gates**:
  - `python3 -m unittest discover -s tests -v` — all pass
  - `python3 eval/run_trials.py --trials 2 --output results/smoke.json` — runs without error
  - `python3 eval/score_results.py --results results/smoke.json` — valid pass@1 output
  - Security: no secrets in code, structured logging throughout, safe error handling
  - PBT: `tests/test_properties.py` with Hypothesis round-trip + invariant tests
