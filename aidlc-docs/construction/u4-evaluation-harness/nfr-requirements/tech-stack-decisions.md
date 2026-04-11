# Tech Stack Decisions — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Decision Table

| Component | Technology | Rationale |
|---|---|---|
| Agent HTTP client | `aiohttp.ClientSession` | Consistent with U2 (MCP Toolbox) and U5 (SchemaIntrospector); avoids introducing `httpx` as a second HTTP library |
| LLM judge client | `openai.AsyncOpenAI` | Same SDK as orchestrator (U1); no new dependency; supports structured JSON output via `response_format` |
| CLI framework | `argparse` (stdlib) | No extra dependency; consistent with `probe_runner.py` (U5) |
| JSON serialization | Pydantic `.model_dump()` + `json.dumps()` | Consistent with all other units; no additional library |
| Async runtime | `asyncio` (stdlib) | Consistent with all other units |
| File I/O | `pathlib.Path` (stdlib) | Consistent with U3 (KnowledgeBase, MemoryManager) |
| Concurrency control | `asyncio.Semaphore(5)` | Limits concurrent agent calls without thread overhead |

---

## NFR Patterns

### Pattern 1: AppendOnlyScoreWriter

**Purpose**: Enforce immutability of the score log.

```python
class ScoreLog:
    @staticmethod
    def append(result: BenchmarkResult, results_dir: Path) -> None:
        path = results_dir / "score_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(result.model_dump()) + "\n"
        with open(path, "a", encoding="utf-8") as f:  # "a" = append, never truncate
            f.write(line)
```

Rule enforced: `"a"` mode only. The string `"w"` must never appear in any ScoreLog I/O call.

---

### Pattern 2: SemaphoreThrottledCaller

**Purpose**: Prevent benchmark from overwhelming the agent with concurrent HTTP calls.

```python
_CONCURRENCY = 5
_sem = asyncio.Semaphore(_CONCURRENCY)

async def _call_agent(session, agent_url, question) -> dict:
    async with _sem:
        async with session.post(
            f"{agent_url}/query",
            json={"question": question},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
```

---

### Pattern 3: FailSafeTrialRunner

**Purpose**: Ensure HTTP failures record as `passed=False` rather than aborting the run.

```python
async def _run_trial(query, trial_index, ...) -> TrialRecord:
    try:
        data = await _call_agent(session, agent_url, query.question)
        # ... build TrialRecord from data ...
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return TrialRecord(
            query_id=query.id,
            trial_index=trial_index,
            question=query.question,
            agent_answer="http_error",
            agent_confidence=0.0,
            session_id="",
            passed=False,
            elapsed_ms=0.0,
        )
```

---

### Pattern 4: WaterfallScorer

**Purpose**: Call ExactMatch first; call LLMJudge only on failure. Minimizes LLM API cost.

```python
async def _score_trial(trial: TrialRecord, expected: Any) -> TrialRecord:
    exact = ExactMatchScorer.score(trial.agent_answer, expected)
    trial.exact_match_passed = exact
    if exact:
        trial.passed = True
        return trial
    # Waterfall: only reach here when exact match failed
    verdict = await LLMJudgeScorer.score(trial.question, trial.agent_answer, expected)
    trial.judge_verdict = verdict
    trial.passed = verdict.passed
    return trial
```

---

## Dependencies

### New (U4-only)
| Library | Purpose | Already in requirements.txt |
|---|---|---|
| `aiohttp` | Agent HTTP calls | Yes (used by U2, U5) |
| `openai` | LLM judge calls | Yes (used by U1) |

### No New Dependencies
U4 introduces no libraries that are not already required by the project. `argparse`, `asyncio`, `pathlib`, `json`, and `uuid` are all stdlib.

---

## PBT Settings

```python
# tests/unit/strategies.py additions
INVARIANT_SETTINGS["PBT-U4-01"] = settings(max_examples=500, deadline=timedelta(milliseconds=50))
INVARIANT_SETTINGS["PBT-U4-02"] = settings(max_examples=200, deadline=timedelta(milliseconds=500))
```

PBT-U4-01 deadline is 50ms (ExactMatchScorer is pure CPU — 1ms per example budget).  
PBT-U4-02 deadline is 500ms (file I/O round-trip; tmpdir used in test fixture).
