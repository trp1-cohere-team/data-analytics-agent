# Business Rules — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Scoring Rules

### BR-U4-01: ExactMatch Numeric Tolerance (Q1=B)
When expected answer is numeric, the agent's string answer passes ExactMatch if and only if:
```
abs(actual_float - expected) / max(abs(expected), 1.0) <= 0.01
```
The denominator `max(abs(expected), 1.0)` prevents division-by-zero when expected=0.

### BR-U4-02: ExactMatch String Normalization (Q2=A)
When expected answer is a string, comparison is case-insensitive with leading/trailing whitespace stripped:
```
actual.strip().lower() == expected.strip().lower()
```
No punctuation removal. No Unicode normalization beyond what Python `str.lower()` provides.

### BR-U4-03: ExactMatch List Comparison
When expected answer is a list, the agent's answer must:
1. Parse as a valid JSON array
2. Have the same length as expected
3. Pass element-wise `ExactMatchScorer.score()` for each pair in order
If any element fails, the whole answer fails.

### BR-U4-04: LLMJudge Waterfall Activation (Q3=B)
The LLM judge is called **only when ExactMatch returns False**. This is a strict waterfall:
- ExactMatch passes → LLMJudge is never called
- ExactMatch fails → LLMJudge is always called
There is no direct-to-LLMJudge path for any query category.

### BR-U4-05: Final Verdict Derivation
`TrialRecord.passed` is set as follows:
- `exact_match_passed == True` → `passed = True`, `judge_verdict = None`
- `exact_match_passed == False` AND `judge_verdict.passed == True` → `passed = True`
- `exact_match_passed == False` AND `judge_verdict.passed == False` → `passed = False`

---

## Pass@1 Rules

### BR-U4-06: Pass@1 Is First Trial Only (Q5=A)
`pass_at_1` for a query is `1.0` if `trials[0].passed == True`, else `0.0`.  
Trials with index ≥ 1 are recorded in traces for statistical analysis but do NOT affect the regression score.

### BR-U4-07: Aggregate Pass@1
`BenchmarkResult.pass_at_1 = mean(per_query_scores.values())`.  
If no queries were run (`total_queries == 0`), `pass_at_1 = 0.0`.

---

## Regression Rules

### BR-U4-08: Regression Gate (Q6=A)
A run FAILS regression if and only if `current pass@1 < previous pass@1`.  
There is no tolerance band — any drop is a regression.

### BR-U4-09: No-Baseline Auto-Pass (Q7=A)
When `score_log.jsonl` contains no prior run (file absent or empty, or no entry with a different `run_id`):
- `RegressionResult.passed = True`
- `RegressionResult.previous_score = 0.0`
- `RegressionResult.delta = current pass@1`
- `RegressionResult.failed_queries = []`
This allows the first run to establish the baseline without manual intervention.

### BR-U4-10: Regression Failed Queries
`failed_queries` in `RegressionResult` lists only queries where:
- `previous per_query_score >= 1.0` (was passing before)
- `current per_query_score < 1.0` (is failing now)
Queries that were already failing before are excluded from `failed_queries`.

---

## I/O Integrity Rules

### BR-U4-11: Score Log Is Append-Only
`results/score_log.jsonl` MUST ONLY be opened in append mode (`"a"`). The file must never be truncated, overwritten, or rewritten. Each run appends exactly one line (one serialized `BenchmarkResult`).

### BR-U4-12: Trace Files Are Write-Once
Each trace file `results/traces/{run_id}/{query_id}_trial_{n}.json` is written once and never modified. If a file at that path already exists (duplicate run_id + query_id + trial_index), raise `ValueError`.

### BR-U4-13: results_dir Creation
Both `results/` and `results/traces/{run_id}/` directories must be created (`mkdir parents=True, exist_ok=True`) before writing. The harness must not require pre-existing directories.

---

## Concurrency Rules

### BR-U4-14: Trial Concurrency Limit (Q4=B)
No more than 5 HTTP calls to the agent may be in-flight simultaneously per benchmark run. Enforced via `asyncio.Semaphore(5)`. This applies across ALL queries and trials in a run.

### BR-U4-15: LLMJudge Concurrency
The LLMJudgeScorer may be called concurrently within the semaphore limit. No additional serialization is needed for LLM judge calls.

---

## CLI Rules

### BR-U4-16: Non-Zero Exit on Regression
`eval/run_benchmark.py` MUST call `sys.exit(1)` when `regression.passed == False`. This enables CI pipelines to detect regressions from the process exit code.

### BR-U4-17: Zero Exit on Success
When `regression.passed == True`, the process exits with `sys.exit(0)` (implicit on clean return).

---

## LLM Judge Rules

### BR-U4-18: Judge Model
The LLM judge uses `settings.OPENROUTER_MODEL` (same model as the agent). The judge call is a separate `openai.AsyncOpenAI` client instance, not the agent's own client, to avoid coupling lifecycles.

### BR-U4-19: Judge Parse Failure
If the LLM judge returns unparseable JSON (malformed or missing required fields), the scorer returns:
```python
JudgeVerdict(passed=False, rationale="judge_parse_error", confidence=0.0)
```
This treats parse failures as conservative failures (the answer is marked wrong, not skipped).

### BR-U4-20: Judge Response Format
The judge system prompt instructs the LLM to return JSON only (no markdown, no prose). The `response_format={"type": "json_object"}` parameter is set on the API call to enforce structured output where the API supports it.

---

## Validation Rules

### BR-U4-21: Agent HTTP Error Handling
If the agent HTTP call returns a non-2xx status or raises a connection error:
- The trial is recorded with `passed=False`, `agent_answer="http_error"`, `agent_confidence=0.0`
- The error is logged at WARNING level (no agent internals in log — BR-U1-01 style)
- The trial contributes `0.0` to pass@1
- The benchmark run continues (fail-safe, not fail-fast)

### BR-U4-22: Agent Timeout
Each agent HTTP call has a 60-second timeout. If exceeded, treated as BR-U4-21 (failed trial, run continues).

### BR-U4-23: Empty Query List
If `queries` is empty, `EvaluationHarness.run()` returns:
```python
BenchmarkResult(run_id=..., pass_at_1=0.0, total_queries=0, ...)
```
and `RegressionSuite.check()` treats this as `current=0.0` vs `previous` (may be a regression if baseline exists).
