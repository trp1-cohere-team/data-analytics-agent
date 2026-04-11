# NFR Requirements — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Performance Requirements

| ID | Requirement | Target | Notes |
|---|---|---|---|
| PERF-U4-01 | Full benchmark run (50 queries × 1 trial) | ≤ 10 minutes wall clock | Semaphore(5); assumes < 10s per agent call normally |
| PERF-U4-02 | ExactMatchScorer per call | < 1 ms | Pure CPU — no I/O, no LLM |
| PERF-U4-03 | LLMJudgeScorer per call | < 30 s | Bounded by OpenRouter API latency |
| PERF-U4-04 | ScoreLog.append() | < 5 ms | Single file append write |
| PERF-U4-05 | QueryTraceRecorder.write() | < 10 ms | Single JSON file write; mkdir is cached after first call |

---

## Reliability Requirements

| ID | Requirement | Behaviour |
|---|---|---|
| REL-U4-01 | Per-trial HTTP failures are non-fatal | Fail-safe: error recorded as `passed=False`, run continues |
| REL-U4-02 | Agent call timeout: 60 seconds | Treated as HTTP failure (REL-U4-01) |
| REL-U4-03 | LLM judge parse error is non-fatal | Returns `JudgeVerdict(passed=False, rationale="judge_parse_error", confidence=0.0)` |
| REL-U4-04 | Empty query list is handled | Returns `BenchmarkResult` with `total_queries=0, pass_at_1=0.0` — no exception |
| REL-U4-05 | Score log append is atomic at OS level | Single `f.write(line)` on opened-append fd; no partial-write risk for single-line JSON |

---

## Security Requirements

| ID | Requirement | Implementation |
|---|---|---|
| SEC-U4-01 | No query content in logs | Trial logs include only: `query_id`, `trial_index`, `passed`, `elapsed_ms` — never `question` or `agent_answer` text |
| SEC-U4-02 | Score log is never truncated | File opened exclusively in append mode (`"a"`); write mode (`"w"`) never used |
| SEC-U4-03 | LLM API key not in logs or traces | `settings.OPENROUTER_API_KEY` used in client constructor only; never written to any file |
| SEC-U4-04 | Trace files are write-once | Duplicate path raises `ValueError` before write (BR-U4-12) |
| SEC-U4-05 | No shell injection from query text | Agent called via `aiohttp` with JSON body — no subprocess or shell interpolation |

---

## Property-Based Testing Requirements

| ID | Property | Description | Examples |
|---|---|---|---|
| PBT-U4-01 | ExactMatch self-consistency | `score(str(x), x) == True` for any numeric `x` (value always matches itself) | 500 |
| PBT-U4-02 | ScoreLog round-trip | `append(r)` then `load_last()` returns entry with `run_id == r.run_id` | 200 |

---

## Observability Requirements

### Structured Log Fields (per event type)

**Run start** (INFO):
```
run_id, agent_url, n_trials, total_queries
```

**Trial complete** (DEBUG):
```
run_id, query_id, trial_index, passed, elapsed_ms, scorer_used
```
`scorer_used` ∈ `{"exact_match", "llm_judge"}` — indicates which scorer determined the verdict.

**Run complete** (INFO):
```
run_id, pass_at_1, total_queries, regression_passed, regression_delta
```

No query text, expected answers, or agent answers appear in any log line (SEC-U4-01).

---

## Scalability Notes

U4 is a batch evaluation tool — it does not serve live traffic. Scalability requirements are bounded by the benchmark dataset size:
- Maximum: 1,000 DAB queries × 50 trials = 50,000 agent calls per full run
- Practical: 50–200 queries for CI regression runs
- `Semaphore(5)` provides adequate throughput for both cases without overloading the agent
