# Domain Entities — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Core Entities

### DABQuery
*Imported from `agent/models.py` — defined in shared infrastructure*

One question from the DataAgentBench benchmark dataset.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique query identifier (e.g. `"DAB-001"`) |
| `question` | `str` | Natural language question posed to the agent |
| `expected_answer` | `Any` | Ground-truth answer (numeric, string, or list) |
| `category` | `str` | Query category: `"NUMERIC"`, `"STRING"`, `"LIST"`, `"COMPLEX"` |
| `databases` | `list[str]` | DB types the query spans (e.g. `["postgres", "duckdb"]`) |

---

### BenchmarkResult
*Imported from `agent/models.py` — defined in shared infrastructure*

Aggregated result from one full benchmark run.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | UUID for this run |
| `timestamp` | `float` | Unix epoch when run started |
| `agent_url` | `str` | Base URL of the agent under test |
| `n_trials` | `int` | Number of trials run per query |
| `total_queries` | `int` | Total number of queries in the run |
| `pass_at_1` | `float` | Pass@1 score (0.0–1.0) averaged across queries |
| `per_query_scores` | `dict[str, float]` | Per-query pass@1 score keyed by `DABQuery.id` |
| `notes` | `str` | Optional notes (e.g. `"baseline run"`) |

---

### JudgeVerdict
*Imported from `agent/models.py` — defined in shared infrastructure*

Result from the LLM-as-judge scorer for one trial.

| Field | Type | Description |
|---|---|---|
| `passed` | `bool` | Whether the judge considers the answer correct |
| `rationale` | `str` | Judge's reasoning (stored but not used for scoring logic) |
| `confidence` | `float` | Judge's confidence in its verdict (0.0–1.0) |

---

### RegressionResult
*Imported from `agent/models.py` — defined in shared infrastructure*

Outcome of running the regression suite against a completed benchmark.

| Field | Type | Description |
|---|---|---|
| `passed` | `bool` | True if current run passes regression gate |
| `current_score` | `float` | pass@1 of the most recent run |
| `previous_score` | `float` | pass@1 of the last recorded run in score_log.jsonl |
| `delta` | `float` | `current_score - previous_score` (negative = regression) |
| `failed_queries` | `list[str]` | Query IDs that passed previously but failed now |

---

### TrialRecord
*Internal to `eval/harness.py` — not exported*

One trial for one query during a benchmark run. Ephemeral — used only during run execution before being written to disk by QueryTraceRecorder.

| Field | Type | Description |
|---|---|---|
| `query_id` | `str` | `DABQuery.id` this trial belongs to |
| `trial_index` | `int` | Trial number (0-based within this query) |
| `question` | `str` | Question sent to agent |
| `agent_answer` | `str` | Answer returned by agent (`OrchestratorResult.answer`) |
| `agent_confidence` | `float` | Confidence from agent response |
| `session_id` | `str` | Session ID from agent response |
| `exact_match_passed` | `bool \| None` | Result of ExactMatch scorer (None if skipped) |
| `judge_verdict` | `JudgeVerdict \| None` | Result of LLMJudge scorer (None if not needed) |
| `passed` | `bool` | Final verdict: exact_match_passed OR judge_verdict.passed |
| `elapsed_ms` | `float` | Agent HTTP call duration |

---

### ScoreLogEntry
*Internal serialization format for `results/score_log.jsonl`*

Each line in the score log is a serialized `BenchmarkResult` (JSON). No additional wrapper — one `BenchmarkResult` per line.

---

### TraceFile
*Serialized to `results/traces/{run_id}/{query_id}_trial_{n}.json`*

JSON file containing one `TrialRecord` per file. Fields include all `TrialRecord` attributes plus the full `OrchestratorResult.query_trace` (list of `TraceStep`).

---

## Entity Relationships

```
EvaluationHarness
    |
    +-- BenchmarkRunner ---------> runs (N trials) per DABQuery
    |       |                           |
    |       |                           +--> HTTP POST /query --> Agent
    |       |                           +--> TrialRecord (ephemeral)
    |
    +-- ExactMatchScorer --------> scores TrialRecord (numeric/string)
    |
    +-- LLMJudgeScorer ----------> scores TrialRecord (when ExactMatch fails)
    |       |
    |       +--> LLM API (GPT-4o judge call)
    |
    +-- QueryTraceRecorder ------> writes TrialRecord --> TraceFile
    |
    +-- ScoreLog ----------------> appends BenchmarkResult --> score_log.jsonl
    |
    +-- RegressionSuite ---------> reads last BenchmarkResult from score_log.jsonl
                                   produces RegressionResult
```
