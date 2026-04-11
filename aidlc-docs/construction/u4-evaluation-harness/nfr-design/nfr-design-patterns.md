# NFR Design Patterns — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Pattern Summary

| # | Name | Category | Addresses |
|---|---|---|---|
| 1 | AppendOnlyScoreWriter | Security / I/O Integrity | SEC-U4-02, BR-U4-11 |
| 2 | SemaphoreThrottledCaller | Scalability / Performance | BR-U4-14, PERF-U4-01 |
| 3 | FailSafeTrialRunner | Resilience | REL-U4-01, REL-U4-02, BR-U4-21/22 |
| 4 | WaterfallScorer | Performance / Cost | BR-U4-03/04/05, PERF-U4-02/03 |

---

## Pattern 1: AppendOnlyScoreWriter

**Purpose**: Guarantee that `results/score_log.jsonl` is never truncated or overwritten — making it an immutable audit trail of benchmark runs.

**Problem**: If `open(path, "w")` is accidentally used, all prior run history is destroyed. No exception is raised; the data is silently lost.

**Solution**:
```python
class ScoreLog:
    @staticmethod
    def append(result: BenchmarkResult, results_dir: Path) -> None:
        path = results_dir / "score_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(result.model_dump()) + "\n"
        # PATTERN: "a" = append only — never "w" or "w+"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    @staticmethod
    def load_last(results_dir: Path) -> BenchmarkResult | None:
        path = results_dir / "score_log.jsonl"
        if not path.exists() or path.stat().st_size == 0:
            return None
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        return BenchmarkResult(**json.loads(lines[-1]))

    @staticmethod
    def load_last_before(run_id: str, results_dir: Path) -> BenchmarkResult | None:
        path = results_dir / "score_log.jsonl"
        if not path.exists():
            return None
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        for line in reversed(lines):
            entry = BenchmarkResult(**json.loads(line))
            if entry.run_id != run_id:
                return entry
        return None
```

**Enforcement**: `ScoreLog` is the only class permitted to read/write `score_log.jsonl`. No other component touches this file directly.

**Addresses**: SEC-U4-02, BR-U4-11

---

## Pattern 2: SemaphoreThrottledCaller

**Purpose**: Limit concurrent HTTP calls to the agent to at most 5 at any time, preventing benchmark load from destabilizing the agent under test.

**Problem**: Without throttling, a 50-query × 5-trial run would attempt 250 concurrent agent calls, potentially causing OOM or rate limiting in the agent itself.

**Solution**:
```python
_AGENT_CONCURRENCY = 5

class BenchmarkRunner:
    async def run_query(
        self, query: DABQuery, agent_url: str, n_trials: int, run_id: str, results_dir: Path
    ) -> float:
        sem = asyncio.Semaphore(_AGENT_CONCURRENCY)
        # All trial coroutines share the same semaphore
        tasks = [
            self._run_trial_guarded(sem, session, query, i, agent_url, run_id, results_dir)
            for i in range(n_trials)
        ]
        trials: list[TrialRecord] = await asyncio.gather(*tasks)
        return 1.0 if trials[0].passed else 0.0

    async def _run_trial_guarded(self, sem, session, query, trial_index, ...) -> TrialRecord:
        async with sem:                           # blocks until slot available
            return await self._run_trial(session, query, trial_index, ...)
```

**Scope**: One `asyncio.Semaphore(_AGENT_CONCURRENCY)` instance per `run_query()` call. All trials for a given query share it.

**Addresses**: BR-U4-14, PERF-U4-01

---

## Pattern 3: FailSafeTrialRunner

**Purpose**: Guarantee that any HTTP failure during a trial (connection refused, timeout, non-2xx) is absorbed and recorded as a failed trial rather than propagating to abort the benchmark run.

**Problem**: If an agent call raises an exception and it propagates, the entire benchmark run fails without recording any partial results or updating the score log.

**Solution**:
```python
async def _run_trial(
    self, session: aiohttp.ClientSession, query: DABQuery, trial_index: int, ...
) -> TrialRecord:
    start = time.monotonic()
    try:
        async with session.post(
            f"{self._agent_url}/query",
            json={"question": query.question},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        elapsed_ms = (time.monotonic() - start) * 1000.0

        trial = TrialRecord(
            query_id=query.id,
            trial_index=trial_index,
            question=query.question,
            agent_answer=data["answer"],
            agent_confidence=data.get("confidence", 0.0),
            session_id=data.get("session_id", ""),
            elapsed_ms=elapsed_ms,
        )
        return await self._score_trial(trial, query.expected_answer)

    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        # PATTERN: absorb, record failure, continue run
        logger.warning("trial_http_error query_id=%s trial=%d", query.id, trial_index)
        return TrialRecord(
            query_id=query.id,
            trial_index=trial_index,
            question=query.question,
            agent_answer="http_error",
            agent_confidence=0.0,
            session_id="",
            exact_match_passed=False,
            judge_verdict=None,
            passed=False,
            elapsed_ms=(time.monotonic() - start) * 1000.0,
        )
```

**Note**: Log line uses `query_id` (metadata only) — never `query.question` (SEC-U4-01).

**Addresses**: REL-U4-01, REL-U4-02, BR-U4-21, BR-U4-22

---

## Pattern 4: WaterfallScorer

**Purpose**: Minimize LLM judge API calls by applying the cheap ExactMatchScorer first and calling LLMJudgeScorer only when necessary.

**Problem**: If LLMJudgeScorer is called for every trial, a 50-query run makes 50 unnecessary LLM calls for numeric or exact-string answers that ExactMatch could handle in < 1ms each.

**Solution**:
```python
async def _score_trial(self, trial: TrialRecord, expected: Any) -> TrialRecord:
    # Stage 1: cheap, synchronous, no LLM
    exact = ExactMatchScorer.score(trial.agent_answer, expected)
    trial.exact_match_passed = exact

    if exact:
        trial.passed = True
        # PATTERN: return immediately — LLMJudge never called
        return trial

    # Stage 2: LLM judge — only reached when ExactMatch fails
    verdict = await LLMJudgeScorer.score(
        trial.question, trial.agent_answer, expected, self._llm_client
    )
    trial.judge_verdict = verdict
    trial.passed = verdict.passed
    return trial
```

**Cost model**: ExactMatch handles ~60–80% of numeric/string answers without LLM cost. LLMJudge only fires for complex or ambiguous answers.

**Addresses**: BR-U4-03, BR-U4-04, BR-U4-05, PERF-U4-02, PERF-U4-03

---

## PBT Hypothesis Strategies

### PBT-U4-01: ExactMatch Self-Consistency (500 examples, deadline 50ms)

```python
# tests/unit/strategies.py addition
from hypothesis import strategies as st

def numeric_values():
    """Generates (value, str_repr) pairs where str(value) should match itself."""
    return st.one_of(
        st.integers(min_value=-10**9, max_value=10**9).map(lambda x: (x, str(x))),
        st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
          .map(lambda x: (x, str(x))),
    )
```

**Property**: `ExactMatchScorer.score(str_repr, value) == True` for all generated pairs.
**Invariant**: A numeric value must always match its own string representation.

### PBT-U4-02: ScoreLog Round-Trip (200 examples, deadline 500ms)

```python
def benchmark_results():
    """Generates arbitrary BenchmarkResult instances."""
    return st.fixed_dictionaries({
        "run_id": st.uuids().map(str),
        "timestamp": st.floats(min_value=0, max_value=2e9, allow_nan=False),
        "agent_url": st.just("http://localhost:8000"),
        "n_trials": st.integers(min_value=1, max_value=10),
        "total_queries": st.integers(min_value=0, max_value=100),
        "pass_at_1": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        "per_query_scores": st.just({}),
        "notes": st.text(max_size=50),
    }).map(lambda d: BenchmarkResult(**d))
```

**Property**: After `ScoreLog.append(result, tmp_dir)`, `ScoreLog.load_last(tmp_dir).run_id == result.run_id`.
**Invariant**: Score log append is always recoverable — what goes in can be read back.

---

## Security Controls Summary

| Control | Pattern | Implementation |
|---|---|---|
| SEC-U4-01 | FailSafeTrialRunner log discipline | `logger.warning("... query_id=%s trial=%d", query.id, trial_index)` — no content fields |
| SEC-U4-02 | AppendOnlyScoreWriter | `open(path, "a")` exclusively |
| SEC-U4-03 | LLM client construction | `openai.AsyncOpenAI(api_key=settings.OPENROUTER_API_KEY)` — key from env only |
| SEC-U4-04 | Write-once trace guard | `if path.exists(): raise ValueError(f"trace already exists: {path}")` |
| SEC-U4-05 | aiohttp JSON body | `session.post(..., json={...})` — no shell subprocess, no string interpolation |
