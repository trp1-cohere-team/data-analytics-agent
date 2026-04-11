# Logical Components — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Component Map

```
eval/harness.py
  EvaluationHarness                      [public API]
    |
    +-- BenchmarkRunner                  [internal]
    |     |-- SemaphoreThrottledCaller   [Pattern 2 — asyncio.Semaphore(5)]
    |     |-- FailSafeTrialRunner        [Pattern 3 — try/except HTTP errors]
    |     |-- WaterfallScorer            [Pattern 4 — ExactMatch then LLMJudge]
    |     |    |-- ExactMatchScorer      [internal — pure function]
    |     |    +-- LLMJudgeScorer        [internal — async LLM call]
    |     |         +-- openai.AsyncOpenAI  [infrastructure — judge client]
    |     +-- aiohttp.ClientSession      [infrastructure — HTTP connection pool]
    |
    +-- QueryTraceRecorder               [internal — write-once file writer]
    |     +-- results/traces/{run_id}/   [filesystem — trace directory]
    |
    +-- ScoreLog                         [internal — AppendOnlyScoreWriter Pattern 1]
    |     +-- results/score_log.jsonl    [filesystem — append-only log]
    |
    +-- RegressionSuite                  [internal — reads ScoreLog]

eval/run_benchmark.py
  CLI entry point                        [argparse — no logic, delegates to EvaluationHarness]
```

---

## Infrastructure Components

| Component | Type | Scope | Purpose |
|---|---|---|---|
| `asyncio.Semaphore(5)` | In-process concurrency gate | Per `run_query()` call | Limits concurrent agent HTTP calls |
| `aiohttp.ClientSession` | HTTP connection pool | Per `EvaluationHarness.run()` call | Reuses TCP connections across trials |
| `openai.AsyncOpenAI` | LLM API client | Per `EvaluationHarness.run()` call | Separate client for judge; not shared with agent internals |
| `results/score_log.jsonl` | Append-only file | Process-global (append mode) | Immutable run history |
| `results/traces/{run_id}/` | Directory tree | Per run | Per-trial JSON trace files |

**Client lifecycle**: `aiohttp.ClientSession` and `openai.AsyncOpenAI` are created at the start of `EvaluationHarness.run()` and closed/released after all trials complete (via `async with` or explicit `.close()`).

---

## Component Responsibilities

### EvaluationHarness (public)

| Method | Responsibility |
|---|---|
| `run(queries, agent_url, n_trials, results_dir)` | Orchestrate: generate run_id, iterate queries, aggregate scores, append to ScoreLog, run RegressionSuite |

### BenchmarkRunner (internal)

| Method | Responsibility |
|---|---|
| `run_query(query, agent_url, n_trials, run_id, results_dir)` | Run N trials for one query; return pass@1 float |
| `_run_trial_guarded(sem, session, query, i, ...)` | Acquire semaphore; delegate to `_run_trial` |
| `_run_trial(session, query, i, agent_url, ...)` | HTTP call to agent; build TrialRecord; call `_score_trial`; write trace |
| `_score_trial(trial, expected)` | WaterfallScorer: ExactMatch → (if fail) LLMJudge |

### ExactMatchScorer (internal, pure)

| Method | Responsibility |
|---|---|
| `score(actual_str, expected) → bool` | Numeric (1% relative tolerance), string (strip+lower), list (element-wise), fallback (str equality) |

### LLMJudgeScorer (internal, async)

| Method | Responsibility |
|---|---|
| `score(question, actual, expected, client) → JudgeVerdict` | Build judge prompt; call LLM; parse JSON response; return JudgeVerdict; safe on parse error |

### QueryTraceRecorder (internal)

| Method | Responsibility |
|---|---|
| `write(trial, run_id, results_dir)` | Write TrialRecord to `results/traces/{run_id}/{query_id}_trial_{n}.json`; raise ValueError if path exists |

### ScoreLog (internal, AppendOnlyScoreWriter)

| Method | Responsibility |
|---|---|
| `append(result, results_dir)` | Append BenchmarkResult JSON line to score_log.jsonl in "a" mode |
| `load_last(results_dir) → BenchmarkResult | None` | Read last line; return None if file empty/absent |
| `load_last_before(run_id, results_dir) → BenchmarkResult | None` | Read backwards; return first entry with different run_id (regression baseline) |

### RegressionSuite (internal)

| Method | Responsibility |
|---|---|
| `check(current_result, results_dir) → RegressionResult` | Load previous run via ScoreLog; compare pass@1; identify failed_queries; return RegressionResult |

### CLI — `eval/run_benchmark.py` (public entry point)

| Responsibility |
|---|
| Parse CLI args (`--agent-url`, `--trials`, `--queries-path`, `--category`) |
| Load DAB queries via `load_dab_queries()` |
| Call `asyncio.run(harness.run(...))` |
| Print summary table |
| `sys.exit(1)` if `regression.passed == False` |

---

## Data Flow Diagram

```
CLI args
   |
   v
load_dab_queries(queries_path, category_filter)
   |
   v  [list[DABQuery]]
EvaluationHarness.run()
   |
   +--[per query]-----------------------------------------------+
   |                                                            |
   v                                                            |
BenchmarkRunner.run_query()                                     |
   |                                                            |
   +--[per trial, max 5 concurrent via Semaphore]---------+     |
   |                                                       |     |
   v                                                       |     |
_run_trial() -------> aiohttp POST /query --> Agent        |     |
   |                  (60s timeout)                        |     |
   v                                                       |     |
TrialRecord (raw)                                          |     |
   |                                                       |     |
   v                                                       |     |
_score_trial()                                             |     |
   |--ExactMatchScorer.score() [pure, < 1ms]               |     |
   |  if passes --> TrialRecord(passed=True)               |     |
   |  if fails  --> LLMJudgeScorer.score() [async LLM]     |     |
   |               --> JudgeVerdict                        |     |
   v                                                       |     |
TrialRecord (scored)                                       |     |
   |                                                       |     |
   v                                                       |     |
QueryTraceRecorder.write()                                 |     |
   --> results/traces/{run_id}/{query_id}_trial_{n}.json   |     |
   |                                                       |     |
   +-------------------------------------------------------+     |
   |                                                            |
   v [pass@1 float per query]                                   |
   +------------------------------------------------------------+
   |
   v [dict[query_id, float]]
BenchmarkResult constructed
   |
   v
ScoreLog.append() --> results/score_log.jsonl ("a" mode)
   |
   v
RegressionSuite.check()
   |-- ScoreLog.load_last_before() --> previous BenchmarkResult
   |-- compare pass@1
   v
RegressionResult
   |
   v
CLI: print summary + sys.exit(0 or 1)
```

---

## Extension Compliance

| Extension | Status | Notes |
|---|---|---|
| Security Baseline | N/A for U4-specific rules | SEC-U4-01/02/03/04/05 enforced via patterns above |
| Property-Based Testing | Enforced | PBT-U4-01 (500 examples, ExactMatch self-consistency), PBT-U4-02 (200 examples, ScoreLog round-trip) |
