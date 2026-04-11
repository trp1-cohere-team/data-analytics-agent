# U4 Code Generation Plan
# Unit 4 — Evaluation Harness

**Status**: In Progress  
**Date**: 2026-04-11

---

## Unit Context

**Requirements**: Batch evaluation CLI — DAB benchmark runner, ExactMatch + LLMJudge scoring, append-only score log, regression gate  
**Dependencies**: `agent/models.py` (BenchmarkResult, DABQuery, JudgeVerdict, RegressionResult), `agent/config.py` (settings), `utils/benchmark_wrapper.py` (load_dab_queries)  
**Files Produced**:
- `eval/__init__.py` — package marker
- `eval/harness.py` — EvaluationHarness + all internal sub-components
- `eval/run_benchmark.py` — CLI entry point (argparse)
- `tests/unit/strategies.py` — add PBT-U4-01/02 settings + strategy functions
- `tests/unit/test_harness.py` — harness + ScoreLog + RegressionSuite tests + PBT-U4-02
- `tests/unit/test_scorers.py` — ExactMatchScorer + LLMJudgeScorer tests + PBT-U4-01
- `aidlc-docs/construction/u4-evaluation-harness/code/code-summary.md`

**Design Sources**:
- `aidlc-docs/construction/u4-evaluation-harness/functional-design/`
- `aidlc-docs/construction/u4-evaluation-harness/nfr-requirements/`
- `aidlc-docs/construction/u4-evaluation-harness/nfr-design/`

---

## Extension Compliance

| Extension | Status | Notes |
|---|---|---|
| Security Baseline | Enforced | SEC-U4-01 (no content in logs), SEC-U4-02 (append-only score log), SEC-U4-03 (API key from env), SEC-U4-04 (trace write-once), SEC-U4-05 (no shell injection) |
| Property-Based Testing | Enforced | 2 blocking PBT properties (PBT-U4-01, PBT-U4-02) |

---

## Code Generation Steps

- [x] **Step 1** — Create `eval/__init__.py`  
  Package marker; exports `EvaluationHarness`.

- [x] **Step 2** — Create `eval/harness.py`  
  Single file containing all internal sub-components:
  - `TrialRecord` — dataclass with all trial fields (query_id, trial_index, question, agent_answer, agent_confidence, session_id, exact_match_passed, judge_verdict, passed, elapsed_ms)
  - `ExactMatchScorer` — static `score(actual_str, expected)`: numeric (1% relative, Q1=B), string (strip+lower, Q2=A), list (element-wise), fallback
  - `LLMJudgeScorer` — async `score(question, actual, expected, client)`: judge prompt → JSON parse → JudgeVerdict; parse error → `JudgeVerdict(passed=False, rationale="judge_parse_error", confidence=0.0)` (BR-U4-19)
  - `QueryTraceRecorder` — static `write(trial, run_id, results_dir)`: write-once guard (BR-U4-12), `mkdir parents=True, exist_ok=True` (BR-U4-13)
  - `ScoreLog` — static `append(result, results_dir)`: "a" mode only (Pattern 1 / SEC-U4-02); `load_last(results_dir)`; `load_last_before(run_id, results_dir)`
  - `RegressionSuite` — static `check(current_result, results_dir)`: zero-tolerance gate (Q6=A); auto-pass on no baseline (Q7=A); `failed_queries` via set intersection (BR-U4-10)
  - `BenchmarkRunner` — `run_query(query, agent_url, n_trials, run_id, results_dir, session, sem, llm_client)`: `asyncio.gather` with Semaphore (Pattern 2); `_run_trial_guarded`; `_run_trial` with FailSafeTrialRunner (Pattern 3); `_score_trial` with WaterfallScorer (Pattern 4); pass@1 = `trials[0].passed` (Q5=A)
  - `EvaluationHarness` — `run(queries, agent_url, n_trials, results_dir)`: creates run_id, aiohttp.ClientSession, openai.AsyncOpenAI, Semaphore; calls BenchmarkRunner per query; builds BenchmarkResult; appends ScoreLog; runs RegressionSuite; structured logging (SEC-U4-01)
  - `_JUDGE_SYSTEM_PROMPT` — module-level constant (judge system message)
  - `_AGENT_CONCURRENCY = 5` — module-level constant

- [x] **Step 3** — Create `eval/run_benchmark.py`  
  CLI entry point:
  - `argparse` with `--agent-url` (required), `--trials` (default 1), `--queries-path` (default "signal/"), `--category` (optional)
  - `load_dab_queries(path, filter)` from `utils.benchmark_wrapper`
  - `asyncio.run(harness.run(queries, agent_url, n_trials))`
  - Print BenchmarkResult summary table
  - Print RegressionResult (PASS/FAIL + delta)
  - `sys.exit(1)` on regression failure (BR-U4-16)

- [x] **Step 4** — Update `tests/unit/strategies.py`  
  Add U4 invariant settings:
  - `"PBT-U4-01": settings(max_examples=500, deadline=timedelta(milliseconds=50))`
  - `"PBT-U4-02": settings(max_examples=200, deadline=timedelta(milliseconds=500))`
  Add `numeric_values()` composite strategy for PBT-U4-01.
  Add `benchmark_results()` composite strategy for PBT-U4-02.

- [x] **Step 5** — Create `tests/unit/test_scorers.py`  
  Unit tests + PBT-U4-01:
  - ExactMatch: integer self-match passes
  - ExactMatch: float self-match passes (1% tolerance)
  - ExactMatch: value within 1% tolerance passes
  - ExactMatch: value beyond 1% tolerance fails
  - ExactMatch: string case-insensitive match passes
  - ExactMatch: string with whitespace passes (strip applied)
  - ExactMatch: list correct element-wise passes
  - ExactMatch: list wrong length fails
  - ExactMatch: non-parseable string for numeric expected fails
  - LLMJudgeScorer: valid JSON response → correct JudgeVerdict fields
  - LLMJudgeScorer: malformed JSON → `JudgeVerdict(passed=False, rationale="judge_parse_error", confidence=0.0)`
  - **PBT-U4-01**: `ExactMatchScorer.score(str(x), x) == True` for all numeric x (500 examples)

- [x] **Step 6** — Create `tests/unit/test_harness.py`  
  Unit tests + PBT-U4-02:
  - ScoreLog: `load_last()` returns None when file absent
  - ScoreLog: append then load_last returns same run_id
  - ScoreLog: multiple appends — load_last returns last run_id
  - ScoreLog: `load_last_before()` returns second-to-last, skipping current run_id
  - RegressionSuite: no baseline → auto-pass (BR-U4-09)
  - RegressionSuite: current >= previous → passed=True (Q6=A)
  - RegressionSuite: current < previous → passed=False (BR-U4-08)
  - RegressionSuite: identifies failed_queries correctly (BR-U4-10)
  - BenchmarkRunner: ExactMatch pass → `judge_verdict=None` (WaterfallScorer early exit)
  - BenchmarkRunner: ExactMatch fail → LLMJudge called (WaterfallScorer stage 2)
  - BenchmarkRunner: HTTP error → trial recorded as `passed=False`, no exception raised (FailSafeTrialRunner)
  - EvaluationHarness.run(): returns BenchmarkResult with correct pass_at_1
  - EvaluationHarness.run(): appends to ScoreLog
  - **PBT-U4-02**: `ScoreLog.append(r)` + `load_last()` → `run_id == r.run_id` (200 examples)

- [x] **Step 7** — Create `aidlc-docs/construction/u4-evaluation-harness/code/code-summary.md`  
  Summary table of all generated files, key design decisions, PBT properties, security compliance.

---

## Completion Criteria

- All 7 steps marked [x]
- Application code in `eval/` and `tests/unit/` (never in aidlc-docs/)
- Security rules: SEC-U4-01 (no content in logs), SEC-U4-02 (append-only score log), SEC-U4-03 (API key from env), SEC-U4-04 (write-once trace), SEC-U4-05 (no shell injection)
- 2 PBT properties present: PBT-U4-01 (ExactMatch self-consistency, 500 examples), PBT-U4-02 (ScoreLog round-trip, 200 examples)
- 4 NFR patterns implemented: AppendOnlyScoreWriter, SemaphoreThrottledCaller, FailSafeTrialRunner, WaterfallScorer
