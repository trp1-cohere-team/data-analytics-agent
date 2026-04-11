# U4 Code Summary — Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Status**: Complete  
**Date**: 2026-04-11

---

## Generated Files

| File | Description | Lines |
|---|---|---|
| `eval/__init__.py` | Package marker; exports `EvaluationHarness` | 3 |
| `eval/harness.py` | All 7 internal components + public EvaluationHarness | ~285 |
| `eval/run_benchmark.py` | CLI entry point (argparse); `sys.exit(1)` on regression | ~80 |
| `tests/unit/strategies.py` | Added PBT-U4-01/02 settings + `numeric_values()` + `benchmark_results()` | +35 |
| `tests/unit/test_scorers.py` | ExactMatchScorer (12 cases) + LLMJudgeScorer (5 cases) + PBT-U4-01 | ~145 |
| `tests/unit/test_harness.py` | ScoreLog (6 cases) + RegressionSuite (5 cases) + BenchmarkRunner (3 cases) + Harness (2 cases) + PBT-U4-02 | ~190 |

---

## Internal Components (`eval/harness.py`)

| Component | Pattern | Purpose |
|---|---|---|
| `TrialRecord` | — | Ephemeral per-trial result dataclass; serialized by QueryTraceRecorder |
| `ExactMatchScorer` | WaterfallScorer stage 1 | Pure scorer: 1% relative numeric (Q1=B), strip+lower string (Q2=A), element-wise list |
| `LLMJudgeScorer` | WaterfallScorer stage 2 | Async LLM judge; single JSON response (Q10=A); parse error → `passed=False` (BR-U4-19) |
| `QueryTraceRecorder` | SEC-U4-04 | Write-once trace files at `results/traces/{run_id}/{query_id}_trial_{n}.json`; `ValueError` on duplicate |
| `ScoreLog` | AppendOnlyScoreWriter (Pattern 1) | Append-only `score_log.jsonl`; `"a"` mode exclusively; `load_last()` + `load_last_before()` |
| `RegressionSuite` | — | Zero-tolerance gate (Q6=A); auto-pass on no baseline (Q7=A); `failed_queries` via set intersection |
| `BenchmarkRunner` | Patterns 2, 3, 4 | `asyncio.Semaphore(5)` concurrency; FailSafe HTTP catch; WaterfallScorer dispatch |
| `EvaluationHarness` | — | Public orchestrator; creates run_id, session, LLM client; aggregates scores; calls ScoreLog + RegressionSuite |

---

## Design Decisions Implemented

| Decision | Code Location | Description |
|---|---|---|
| Q1=B: 1% relative numeric tolerance | `harness.py:ExactMatchScorer.score()` | `abs(actual-expected) / max(abs(expected), 1.0) <= 0.01` |
| Q2=A: Strip + lowercase string | `harness.py:ExactMatchScorer.score()` | `actual.strip().lower() == expected.strip().lower()` |
| Q3=B: LLMJudge waterfall | `harness.py:BenchmarkRunner._score_trial()` | Early return on ExactMatch pass; LLMJudge only on failure |
| Q4=B: Semaphore(5) concurrency | `harness.py:BenchmarkRunner.run_query()` | `asyncio.Semaphore(_AGENT_CONCURRENCY)` shared across all trial tasks |
| Q5=A: pass@1 = first trial | `harness.py:BenchmarkRunner.run_query()` | `1.0 if trials[0].passed else 0.0` |
| Q6=A: Zero-tolerance regression | `harness.py:RegressionSuite.check()` | `current.pass_at_1 >= previous.pass_at_1` (strict) |
| Q7=A: No-baseline auto-pass | `harness.py:RegressionSuite.check()` | `previous is None → RegressionResult(passed=True, previous_score=0.0)` |
| Q8=B: Trace nested by run | `harness.py:QueryTraceRecorder.write()` | `results/traces/{run_id}/{query_id}_trial_{n}.json` |
| Q9=C: Full CLI args | `run_benchmark.py` | `--agent-url`, `--trials`, `--queries-path`, `--category` |
| Q10=A: Single JSON judge response | `harness.py:LLMJudgeScorer.score()` | `response_format={"type": "json_object"}`; one call per query |
| BR-U4-16: sys.exit(1) on regression | `run_benchmark.py:main()` | `sys.exit(0 if regression.passed else 1)` |
| BR-U4-19: Judge parse error safe | `harness.py:LLMJudgeScorer.score()` | `except Exception → JudgeVerdict(passed=False, rationale="judge_parse_error")` |

---

## PBT Properties

| ID | File | Description | Examples |
|---|---|---|---|
| PBT-U4-01 | `test_scorers.py` | `ExactMatchScorer.score(str(x), x) == True` for any numeric x | 500 |
| PBT-U4-02 | `test_harness.py` | `ScoreLog.append(r)` + `load_last()` → `run_id == r.run_id` (round-trip) | 200 |

---

## Security Compliance

| Rule | Status | Implementation |
|---|---|---|
| SEC-U4-01: No content in logs | Compliant | `logger.warning("trial_http_error query_id=%s trial_index=%d", ...)` — no question/answer |
| SEC-U4-02: Score log append-only | Compliant | `open(path, "a")` exclusively; string `"w"` never used on score_log.jsonl |
| SEC-U4-03: API key from env only | Compliant | `openai.AsyncOpenAI(api_key=settings.OPENROUTER_API_KEY)` — never written to file |
| SEC-U4-04: Trace files write-once | Compliant | `if path.exists(): raise ValueError(...)` before write |
| SEC-U4-05: No shell injection | Compliant | `session.post(..., json={...})` — no subprocess, no string interpolation |

---

## Dependencies

| Dependency | Imported from |
|---|---|
| `BenchmarkResult`, `DABQuery`, `JudgeVerdict`, `RegressionResult` | `agent/models.py` |
| `settings` (OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL) | `agent/config.py` |
| `load_dab_queries()` | `utils/benchmark_wrapper.py` |
| `aiohttp.ClientSession` | `aiohttp` (already in requirements.txt) |
| `openai.AsyncOpenAI` | `openai` (already in requirements.txt) |
