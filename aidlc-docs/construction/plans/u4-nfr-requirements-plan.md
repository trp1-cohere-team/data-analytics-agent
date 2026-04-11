# U4 NFR Requirements Plan
# Unit 4 — Evaluation Harness

**Status**: Complete  
**Date**: 2026-04-11

---

## Pre-Analysis Q&A

All answers derived from functional design artifacts and established U1–U5 patterns.

---

### Q1 — Performance: benchmark run time budget

What is the acceptable wall-clock time for a full benchmark run (50 queries × 1 trial)?

**[Answer]**: With `Semaphore(5)` and a 60s per-call timeout, worst-case is `ceil(50/5) × 60s = 600s`. Target: complete within 10 minutes under normal agent latency (< 10s per call → ~120s for 50 queries).

---

### Q2 — Performance: ExactMatchScorer latency

**[Answer]**: Pure CPU — must complete in < 1ms per call (no I/O, no LLM). No additional constraint.

---

### Q3 — Reliability: partial run failure policy

**[Answer]**: Fail-safe (BR-U4-21). HTTP errors/timeouts per trial are recorded as `passed=False` and run continues. The run always produces a `BenchmarkResult` even if all trials fail.

---

### Q4 — Security: score log integrity

**[Answer]**: Score log opened in append mode only (BR-U4-11). No content (query text, answers) written to logs — metadata only (run_id, timestamp, pass@1, query IDs). Matches SEC-U1-01 pattern.

---

### Q5 — Tech stack: HTTP client for agent calls

**[Answer]**: `aiohttp` — consistent with U2 (MCP Toolbox calls) and U5 (SchemaIntrospector). Avoids introducing a second HTTP client library (`httpx`).

---

### Q6 — Tech stack: LLM judge client

**[Answer]**: `openai.AsyncOpenAI` with `base_url=settings.OPENROUTER_BASE_URL` and `api_key=settings.OPENROUTER_API_KEY`. Separate client instance from the agent's own `_llm_client` (BR-U4-18). No retry on judge calls (one attempt only — failed judge = `passed=False`).

---

### Q7 — Tech stack: CLI framework

**[Answer]**: `argparse` (standard library). No extra dependency. Consistent with `probe_runner.py` (U5).

---

### Q8 — PBT: what properties are testable?

**[Answer]**:
- **PBT-U4-01**: `ExactMatchScorer.score(str(x), x)` returns `True` for any numeric `x` within Python float range (self-consistency: a value always matches itself)
- **PBT-U4-02**: `ScoreLog.append(result)` followed by `ScoreLog.load_last()` always returns an entry with `run_id == result.run_id` (round-trip integrity)

---

### Q9 — Observability: what is logged?

**[Answer]**: Structured logs (no content per SEC-U4-01):
- Run start: `run_id`, `agent_url`, `n_trials`, `total_queries`
- Per trial: `query_id`, `trial_index`, `passed`, `elapsed_ms` (no question text, no answer text)
- Run end: `run_id`, `pass_at_1`, `regression_passed`, `delta`

---

## Plan Steps

- [x] **Step 1** — Pre-analyze unit context and pre-fill all Q&A decisions
- [x] **Step 2** — Create `aidlc-docs/construction/u4-evaluation-harness/nfr-requirements/nfr-requirements.md`
- [x] **Step 3** — Create `aidlc-docs/construction/u4-evaluation-harness/nfr-requirements/tech-stack-decisions.md`
- [x] **Step 4** — Update aidlc-state.md and audit.md
