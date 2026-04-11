# Business Logic Model — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## 1. EvaluationHarness — Orchestration Logic

`eval/harness.py` is the single public class. All sub-components are internal.

### `EvaluationHarness.run(queries, agent_url, n_trials, results_dir)`

```
INPUT:  queries: list[DABQuery]
        agent_url: str           (e.g. "http://localhost:8000")
        n_trials: int            (default 1 for regression; 50 for full benchmark)
        results_dir: Path        (default Path("results"))

STEPS:
  1. run_id = str(uuid4())
  2. For each query q in queries:
       scores[q.id] = await BenchmarkRunner.run_query(q, agent_url, n_trials, run_id, results_dir)
       # scores[q.id] = pass@1 (float 0.0 or 1.0 from trial index 0)
  3. pass_at_1 = mean(scores.values())  if scores else 0.0
  4. result = BenchmarkResult(
         run_id=run_id,
         timestamp=time.time(),
         agent_url=agent_url,
         n_trials=n_trials,
         total_queries=len(queries),
         pass_at_1=pass_at_1,
         per_query_scores=scores,
     )
  5. ScoreLog.append(result, results_dir)
  6. regression = RegressionSuite.check(result, results_dir)
  7. RETURN result, regression
```

---

## 2. BenchmarkRunner — Trial Execution Logic

### `BenchmarkRunner.run_query(query, agent_url, n_trials, run_id, results_dir) → float`

Returns pass@1 score (0.0 or 1.0) for the query.

```
INPUT:  query: DABQuery, agent_url: str, n_trials: int, run_id: str, results_dir: Path

STEPS:
  semaphore = asyncio.Semaphore(5)   [Q4=B: max 5 concurrent calls]
  trials: list[TrialRecord] = []

  For each i in range(n_trials):  [via asyncio.gather with semaphore]
    async with semaphore:
      start = time.monotonic()
      response = await HTTP POST {agent_url}/query
                        body={"question": query.question}
                        timeout=60s
      elapsed_ms = (time.monotonic() - start) * 1000

      agent_answer = response["answer"]
      agent_confidence = response["confidence"]
      session_id = response["session_id"]

      trial = TrialRecord(
          query_id=query.id,
          trial_index=i,
          question=query.question,
          agent_answer=agent_answer,
          agent_confidence=agent_confidence,
          session_id=session_id,
          elapsed_ms=elapsed_ms,
      )
      trial = await _score_trial(trial, query.expected_answer)
      QueryTraceRecorder.write(trial, run_id, results_dir)
      trials.append(trial)

  pass_at_1 = 1.0 if trials[0].passed else 0.0  [Q5=A: first trial only]
  RETURN pass_at_1
```

### `BenchmarkRunner._score_trial(trial, expected) → TrialRecord`

```
  exact = ExactMatchScorer.score(trial.agent_answer, expected)
  trial.exact_match_passed = exact

  if exact:
      trial.passed = True
      RETURN trial

  # Waterfall: LLMJudge only when ExactMatch fails [Q3=B]
  verdict = await LLMJudgeScorer.score(trial.question, trial.agent_answer, expected)
  trial.judge_verdict = verdict
  trial.passed = verdict.passed
  RETURN trial
```

---

## 3. ExactMatchScorer — Scoring Logic

### `ExactMatchScorer.score(actual_str, expected) → bool`

```
INPUT: actual_str: str  (agent answer — always a string from HTTP response)
       expected: Any    (DABQuery.expected_answer — numeric, str, or list)

CASE 1: expected is numeric (int or float)
  Try parse actual_str as float → actual_num
  If parse fails → RETURN False
  relative_diff = abs(actual_num - expected) / max(abs(expected), 1.0)
  RETURN relative_diff <= 0.01    [Q1=B: 1% relative tolerance]

CASE 2: expected is str
  RETURN actual_str.strip().lower() == expected.strip().lower()  [Q2=A]

CASE 3: expected is list
  Try parse actual_str as JSON list → actual_list
  If parse fails → RETURN False
  If len(actual_list) != len(expected) → RETURN False
  For each pair (a, e) in zip(actual_list, expected):
    if not ExactMatchScorer.score(str(a), e): RETURN False
  RETURN True

CASE 4: expected is None / other
  RETURN str(actual_str).strip() == str(expected).strip()
```

---

## 4. LLMJudgeScorer — Scoring Logic

### `LLMJudgeScorer.score(question, actual, expected) → JudgeVerdict`

```
INPUT: question: str, actual: str, expected: Any

JUDGE PROMPT (system):
  "You are an impartial benchmark evaluator. Your task is to determine if an
   AI agent answered a data analytics question correctly.
   
   Respond with ONLY valid JSON in this exact format:
   {\"passed\": <bool>, \"rationale\": \"<1-2 sentences>\", \"confidence\": <float 0-1>}
   
   Scoring criteria:
   - Numeric answers: accept if within 1% relative tolerance
   - String answers: accept case-insensitive, ignore surrounding whitespace
   - The agent's reasoning style or phrasing does not affect correctness"

JUDGE MESSAGES:
  [{"role": "user", "content":
    "Question: {question}\nExpected: {expected}\nAgent answered: {actual}\n
     Is the agent's answer correct?"}]

LLM CALL:
  client.chat.completions.create(
      model=settings.OPENROUTER_MODEL,
      messages=[system, user],
      response_format={"type": "json_object"},   [Q10=A]
  )

PARSE:
  json.loads(response.choices[0].message.content)
  → JudgeVerdict(passed=..., rationale=..., confidence=...)

ON PARSE ERROR:
  RETURN JudgeVerdict(passed=False, rationale="parse_error", confidence=0.0)
```

---

## 5. QueryTraceRecorder — Trace Writing Logic

### `QueryTraceRecorder.write(trial, run_id, results_dir)`

```
INPUT: trial: TrialRecord, run_id: str, results_dir: Path

path = results_dir / "traces" / run_id / f"{trial.query_id}_trial_{trial.trial_index}.json"
path.parent.mkdir(parents=True, exist_ok=True)

data = trial.model_dump()  (includes all TrialRecord fields)
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

No atomic rename needed — trace files are written once and never updated.

---

## 6. ScoreLog — Append Logic

### `ScoreLog.append(result, results_dir)`

```
INPUT: result: BenchmarkResult, results_dir: Path

path = results_dir / "score_log.jsonl"
path.parent.mkdir(parents=True, exist_ok=True)

line = json.dumps(result.model_dump()) + "\n"

with open(path, "a", encoding="utf-8") as f:  [append mode — never overwrite]
    f.write(line)
```

### `ScoreLog.load_last(results_dir) → BenchmarkResult | None`

```
path = results_dir / "score_log.jsonl"
if not path.exists() or path.stat().st_size == 0:
    RETURN None

lines = path.read_text(encoding="utf-8").strip().splitlines()
RETURN BenchmarkResult(**json.loads(lines[-1]))
```

---

## 7. RegressionSuite — Comparison Logic

### `RegressionSuite.check(current_result, results_dir) → RegressionResult`

```
INPUT: current_result: BenchmarkResult, results_dir: Path

previous = ScoreLog.load_last_before(current_result.run_id, results_dir)
  # reads the SECOND-to-last entry (not the one just appended)

IF previous is None:   [Q7=A: no baseline — first run auto-passes]
    RETURN RegressionResult(
        passed=True,
        current_score=current_result.pass_at_1,
        previous_score=0.0,
        delta=current_result.pass_at_1,
        failed_queries=[],
    )

delta = current_result.pass_at_1 - previous.pass_at_1

# Identify regressions: queries that passed before but fail now  [Q6=A]
previously_passed = {qid for qid, score in previous.per_query_scores.items() if score >= 1.0}
currently_failed  = {qid for qid, score in current_result.per_query_scores.items() if score < 1.0}
failed_queries = sorted(previously_passed & currently_failed)

passed = (current_result.pass_at_1 >= previous.pass_at_1)   [Q6=A: zero tolerance]

RETURN RegressionResult(
    passed=passed,
    current_score=current_result.pass_at_1,
    previous_score=previous.pass_at_1,
    delta=delta,
    failed_queries=failed_queries,
)
```

### `ScoreLog.load_last_before(run_id, results_dir) → BenchmarkResult | None`

```
# Returns the last entry in score_log.jsonl whose run_id != run_id
# (i.e. the previous run, not the one just appended)
lines = path.read_text().strip().splitlines()
for line in reversed(lines):
    entry = BenchmarkResult(**json.loads(line))
    if entry.run_id != run_id:
        RETURN entry
RETURN None
```

---

## 8. run_benchmark.py — CLI Logic

### Entry point: `python -m eval.run_benchmark`

```
ARGS [Q9=C]:
  --agent-url    str      required   Base URL of agent under test
  --trials       int      default=1  Number of trials per query
  --queries-path str      optional   Path to DAB queries JSON/dir (default: "signal/")
  --category     str      optional   Filter queries by category

STEPS:
  1. queries = load_dab_queries(path=queries_path, filter=lambda q: q.category==category if category else None)
  2. harness = EvaluationHarness()
  3. result, regression = asyncio.run(harness.run(queries, agent_url, trials))
  4. Print BenchmarkResult summary
  5. Print RegressionResult (PASS / FAIL with delta)
  6. sys.exit(1) if not regression.passed   (non-zero exit for CI integration)
```
