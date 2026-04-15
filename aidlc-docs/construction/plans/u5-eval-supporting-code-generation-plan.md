# Code Generation Plan — U5: Eval + Supporting Files

## Unit Context
- **Unit**: U5 — Eval + Supporting Files
- **Design Artifact**: `aidlc-docs/construction/u5-eval-supporting/functional-design/business-logic-model.md`
- **Dependencies**: U1 (types, config), U2 (data layer), U3 (runtime), U4 (agent facade)
- **Workspace Root**: `/home/nurye/Desktop/TRP1/week8/OracleForge`

## Stories Implemented by This Unit
- FR-07 DAB evaluation harness (run_trials, run_dab_benchmark, score_results)
- FR-09 Corrections log seed content (3 bootstrapped examples)
- FR-11 Adversarial probes documentation (15 probes across 3 categories)
- PBT-02 Round-trip property tests (ContextPacket, TraceEvent)
- PBT-03 Invariant property tests (classify() categories, pass@1 range, Layer 6 preservation)
- PBT-07 Domain-specific Hypothesis generators
- PBT-08 Hypothesis default shrinking enabled
- PBT-09 hypothesis pinned in requirements.txt
- SEC-03 Structured logging in all eval scripts
- SEC-10 Pinned exact versions in requirements.txt
- SEC-15 Exception handling in all file I/O and agent calls

---

## Steps

### Step 1: Generate `eval/run_trials.py`
- [x] `run_trials(datasets, trials, output_path) -> list[dict]` — FR-07 local trial runner
- [x] `_load_question(query_dir)` — parse query.json (string, array, or object)
- [x] `_load_ground_truth(query_dir)` — read ground_truth.csv first data row
- [x] `_load_db_hints(dataset)` — extract db_type values from db_config.yaml
- [x] `_answer_passes(answer, ground_truth)` — substring heuristic match
- [x] CLI: `--trials N`, `--output path`, `--datasets list`
- [x] Results: `{dataset, query_id, trial, question, answer, confidence, trace_id, pass, ground_truth, duration_s}`
- [x] Logger, SEC-03, SEC-15

### Step 2: Generate `eval/run_dab_benchmark.py`
- [x] `main()` — wraps `run_trials()` for all 12 DAB datasets, FR-07
- [x] Per-dataset pass rate summary printed to stdout
- [x] Overall pass@1 computed and printed
- [x] CLI: `--trials N`, `--output path`, `--datasets list`
- [x] Logger, SEC-03, SEC-15

### Step 3: Generate `eval/score_results.py`
- [x] `compute_pass_at_1(results) -> tuple[float, dict]` — FR-07, PBT-03
- [x] Group by `(dataset, query_id)`, pass if any trial passes
- [x] Clamp to `[0.0, 1.0]` (PBT-03 invariant)
- [x] `score(results_path, output_dir) -> float` — loads JSON, computes scores, writes output files
- [x] Output: `dab_detailed.json` (per-query breakdown) + `dab_submission.json` (summary)
- [x] CLI: `--results path`, `--output-dir path`
- [x] Logger, SEC-03, SEC-15

### Step 4: Generate `tests/test_conductor.py`
- [x] `TestConductorOffline` — 10 unit tests for `OracleForgeConductor`
- [x] Offline mode: `run()` returns `AgentResult`, no API calls
- [x] `answer` is a non-empty string, `confidence` in `[0.0, 1.0]`
- [x] `trace_id` is non-empty string
- [x] Empty question handled gracefully
- [x] Long question (>4096 chars) handled gracefully (SEC-05 truncation)
- [x] `db_hints` defaults to empty list when omitted
- [x] Memory persists across multiple `run()` calls on same session
- [x] `ContextPacket` returned in result has all 6 layers
- [x] `AgentResult.to_dict()` returns plain dict
- [x] Multiple concurrent sessions isolated

### Step 5: Generate `tests/test_context_layering.py`
- [x] `TestBuildContextPacket` — 4 unit tests for `build_context_packet()`
- [x] All 6 layers populated
- [x] Layer 6 (user_question) is the highest-priority layer
- [x] Missing layers default to empty strings
- [x] Backward-compat property aliases work correctly
- [x] `TestAssemblePrompt` — 4 unit tests for `assemble_prompt()`
- [x] Returns a string for any input
- [x] Empty packet returns a string (may be empty)
- [x] Assembled prompt contains the user question
- [x] Schema info (Layer 1) appears when present

### Step 6: Generate `tests/test_failure_diagnostics.py`
- [x] `TestClassify` — 10 unit tests for `FailureDiagnostics.classify()`
- [x] Always returns a `FailureDiagnosis` instance
- [x] `category` is always one of `VALID_FAILURE_CATEGORIES`
- [x] SQL syntax errors → `query` category
- [x] Connection errors → `db-type` category
- [x] Join key mismatch → `join-key` category
- [x] `explanation` field is always a string
- [x] `suggested_fix` field is always a string
- [x] DuckDB query error_type → `query` category
- [x] DuckDB config/policy error_type → `db-type` category
- [x] `classify()` never raises regardless of input

### Step 7: Generate `tests/test_memory.py`
- [x] `TestMemoryManager` — 5 unit tests for `MemoryManager`
- [x] Import does not create files
- [x] `get_memory_context()` returns empty string for new session
- [x] `get_memory_context()` always returns a string
- [x] `save_turn()` lazily creates the session JSONL file
- [x] Session cap enforced at `AGENT_MEMORY_SESSION_ITEMS`

### Step 8: Generate `tests/test_properties.py`
- [x] `TestRoundTripProperties` — PBT-02 round-trip tests
- [x] `ContextPacket.to_dict()` → `from_dict()` round-trip (Hypothesis)
- [x] `ContextPacket.to_dict()` always returns a plain dict
- [x] `TraceEvent.to_dict()` → `from_dict()` round-trip (Hypothesis)
- [x] `TestInvariantProperties` — PBT-03 invariant tests
- [x] `failure_diagnostics.classify()` always returns a valid category (Hypothesis)
- [x] Layer 6 (user_question) always present in assembled prompt (Hypothesis)
- [x] `compute_pass_at_1()` pass@1 always in `[0.0, 1.0]` (Hypothesis)
- [x] `TraceEvent.to_dict()` includes all required fields (Hypothesis)
- [x] Domain-specific `st.builds()` generators (PBT-07)
- [x] Default shrinking enabled; seeds logged on failure (PBT-08)

### Step 9: Generate knowledge base seed files
- [x] `kb/architecture/agent-architecture.md` — system overview, 6-layer context model
- [x] `kb/architecture/tool-scoping.md` — ToolPolicy rules, DB routing logic
- [x] `kb/domain/query-patterns.md` — common SQL/MongoDB patterns per DB type
- [x] `kb/domain/join-key-glossary.md` — join key mappings across DAB datasets
- [x] `kb/evaluation/dab-format.md` — DAB benchmark query/ground_truth format
- [x] `kb/corrections/corrections_log.md` — 3 seeded correction examples (FR-09)

### Step 10: Generate `probes/probes.md`
- [x] Category 1: Schema Confusion (5 probes: SC-01 to SC-05)
- [x] Category 2: Cross-DB Join Traps (5 probes: CJ-01 to CJ-05)
- [x] Category 3: Correction Memory Gaming (5 probes: MG-01 to MG-05)
- [x] Each probe: input, expected behavior, what it tests, fix evidence (FR-11)

### Step 11: Generate project configuration artifacts
- [x] `tools.yaml` — 4 MCP tool descriptors (postgres, mongodb, sqlite, duckdb)
- [x] `requirements.txt` — pinned exact versions (SEC-10): requests, flask, pyyaml, python-dotenv, hypothesis, werkzeug
- [x] `.env.example` — all env vars documented with safe defaults
- [x] `README.md` — project overview, quickstart, architecture, eval instructions

### Step 12: Write markdown code summary
- [x] Save summary at `aidlc-docs/construction/u5-eval-supporting/code/code-summary.md`

### Step 13: Update plan checkboxes and aidlc-state.md
- [x] Mark all steps [x]
- [x] Update aidlc-state.md current stage
