# OracleForge Requirements Clarification Questions

Your specification is detailed and comprehensive. The questions below target genuine gaps and ambiguities that will affect architecture decisions. Please answer each question by filling in the letter after the `[Answer]:` tag.

---

## Question 1: Sandbox Server Inclusion
The `test.md` runbook references `sandbox/sandbox_server.py`, `agent/runtime/worker.py`, and `agent/data_agent/sandbox_client.py` — a Python code execution sandbox not mentioned in the main spec. Should the sandbox execution path be included in this build?

A) Yes — include sandbox server (`sandbox/sandbox_server.py`) and sandbox client (`agent/data_agent/sandbox_client.py`) as an optional code-execution route alongside MCP
B) No — skip the sandbox entirely; MCP toolbox is the only execution path
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 2: Types Module
The architecture doc (`CLAUDE_CODE_ARCHITECTURE_IMPLEMENTATION.md`) references `agent/data_agent/types.py` for shared dataclasses (`AgentResult`, trace structures, etc.) but it is not listed in the directory spec. Should a `types.py` module be created?

A) Yes — create `agent/data_agent/types.py` with all shared dataclasses/TypedDicts (AgentResult, TraceEvent, ContextPacket, etc.)
B) No — define types inline inside each module that uses them (keep imports flat)
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 3: DAB Evaluation Mode
The eval harness must run DAB queries. In offline mode (`AGENT_OFFLINE_MODE=1`), what should the harness do?

A) Run fully with stub/mock LLM responses — return deterministic placeholder answers so all infrastructure (context layering, memory, events) is exercised without any API calls
B) Skip LLM calls entirely and return a fixed stub answer per query — fast validation that the harness scaffold works
C) Fail with a clear error message indicating that online mode is required for meaningful evaluation
D) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 4: DAB Dataset Subset for Smoke Test
The spec lists 12 DAB datasets. For the smoke test and local `run_trials.py`, which datasets should be used?

A) Only `bookreview` — smallest dataset, fastest test, sufficient for smoke validation
B) `bookreview` + `stockmarket` — two datasets to test broader coverage
C) All 12 — full evaluation even for smoke; rely on `--query-limit` flag to cap queries
D) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 5: MCP Toolbox Offline Stub
When `AGENT_USE_MCP=0` or `AGENT_OFFLINE_MODE=1`, the MCP client cannot reach the toolbox server. What should `mcp_toolbox_client.py` return?

A) Return a hardcoded stub tool list + stub query results (defined in `config.py`) — allows full agent pipeline to run offline without any external calls
B) Return empty tool list and raise `OfflineModeError` on any invoke call — forces callers to handle offline gracefully
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 6: Knowledge Base Initial Content
The KB subdirs (`kb/architecture/`, `kb/domain/`, `kb/evaluation/`) need seed documents. How much content should be seeded at build time?

A) Full seed — write 2-3 substantive `.md` documents per subdirectory covering the topics listed in the spec (DAB schema, query patterns, architecture overview, failure categories, scoring method)
B) Minimal seed — write one placeholder `.md` per subdirectory with headers and stub content; developer fills in details
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 7: User Stories
Should User Stories be generated for this project?

A) Yes — generate user stories for the key user types: data analyst querying DBs, evaluator running DAB benchmark, developer running tests
B) No — skip User Stories; requirements are sufficiently detailed in the spec
C) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 8: Security Extension
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)
B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)
X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 9: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)
B) Partial — enforce PBT rules only for pure functions and serialization round-trips (e.g., context layering, failure diagnostics)
C) No — skip all PBT rules
X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 10: Application Design Stage
The project has a fully-specified architecture. Should a formal Application Design stage be executed (component method signatures, service layer contracts) or can we proceed directly to Code Generation?

A) Execute Application Design — generate formal component diagrams, method signatures, and service contracts before coding
B) Skip Application Design — architecture is already specified; proceed directly to Units Generation then Code Generation
C) Other (please describe after [Answer]: tag below)

[Answer]: B

---

Please fill in all `[Answer]:` tags and let me know when done.
