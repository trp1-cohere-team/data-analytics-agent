# Unit of Work Plan
# The Oracle Forge — Data Analytics Agent

**Status**: Answers received — proceeding to generation  
**Date**: 2026-04-11

---

## Plan Checkboxes

- [x] Answer decomposition questions (below)
- [x] Generate unit-of-work.md — unit definitions and responsibilities
- [x] Generate unit-of-work-dependency.md — dependency matrix and build order
- [x] Generate unit-of-work-story-map.md — component-to-unit assignment
- [x] Validate unit boundaries and dependencies
- [x] Update aidlc-state.md and audit.md

---

## Confirmed Units (from Application Design)

The 5 units are already established. These questions address cross-cutting implementation decisions that will directly affect code generation for all units.

| Unit | Components |
|---|---|
| U1 — Agent Core & API | AgentAPI, Orchestrator, ContextManager, CorrectionEngine |
| U2 — Multi-DB Execution Engine | MultiDBEngine + sub-components (QueryRouter, 4 Connectors, JoinKeyResolver, ResultMerger) |
| U3 — Knowledge Base & Memory | KnowledgeBase, MemoryManager |
| U4 — Evaluation Harness | EvaluationHarness + sub-components |
| U5 — Utilities & Adversarial Probes | SchemaIntrospector, MultiPassRetriever, JoinKeyUtils, BenchmarkWrapper, ProbeLibrary |

---

## Decomposition Questions

### Question 1: Shared Data Models Location
Pydantic models used across multiple units (e.g., `QueryPlan`, `SubQuery`, `ContextBundle`, `ExecutionResult`, `ExecutionFailure`, `CorrectionEntry`, `TraceStep`) need a home. Where should they live?

A) Dedicated shared module — `agent/models.py` (or `agent/types.py`): all shared dataclasses/Pydantic models in one file, imported by any unit that needs them
B) Co-located with their primary owner — e.g., `QueryPlan` in `agent/execution/`, `ContextBundle` in `agent/context/`: each unit owns its types, others import from it
C) Split — request/response models in `agent/api/models.py`; internal data models in `agent/models.py`
D) Other (describe after [Answer]: tag)

[Answer]: A

---

### Question 2: Configuration Management
Units need environment variables and runtime config (OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MCP_TOOLBOX_URL, rate limits, max iterations, etc.). How should config be managed?

A) Central config module — `agent/config.py` using `pydantic-settings` (reads `.env` file + environment variables); all units import from it
B) Environment variables read directly at call site — each module reads `os.environ` where needed
C) Other (describe after [Answer]: tag)

[Answer]: A

---

### Question 3: Construction Order
The execution plan listed U1+U2 first, then U3, U4, U5. But U1 (Orchestrator) calls U2 (MultiDBEngine) which calls U5 utilities (JoinKeyUtils, SchemaIntrospector). What construction order should be followed?

A) Dependency-first — build U5 (utilities) → U2 (execution, depends on U5) → U1 (orchestrator, depends on U2+U5) → U3 (KB/memory, independent) → U4 (eval, independent). Each unit compiles against real imports, not stubs.
B) Top-down — build U1 first (with stub/mock interfaces for U2/U5), then U2, then remaining. Allows API layer to be tested early.
C) Original plan order — U1+U2 in parallel (with interface contracts agreed upfront), then U3, U4, U5.
D) Other (describe after [Answer]: tag)

[Answer]: A

---

### Question 4: Integration Test Location
Tests that cross unit boundaries (e.g., Orchestrator → MultiDBEngine → MCP Toolbox, or full query end-to-end) need a home. Where should they live?

A) `tests/integration/` at workspace root — separate from each unit's own `tests/` folder; run separately from unit tests
B) Inside the primary unit's test folder — e.g., Orchestrator integration tests in `agent/tests/test_integration.py`
C) `eval/` handles end-to-end testing; unit-level tests stay in each unit's `tests/` folder; no separate integration folder needed
D) Other (describe after [Answer]: tag)

[Answer]: A

---

Please fill in the [Answer]: tags above and let me know when done.
