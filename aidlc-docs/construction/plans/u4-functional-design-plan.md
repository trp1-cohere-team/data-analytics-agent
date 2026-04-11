# U4 Functional Design Plan
# Unit 4 — Evaluation Harness

**Status**: Complete  
**Date**: 2026-04-11

---

## Unit Context

**Unit**: U4 — Evaluation Harness  
**Build Position**: 5th (after U1 — calls AgentAPI via HTTP)  
**Layer**: Evaluation  
**Files Produced**:
- `aidlc-docs/construction/u4-evaluation-harness/functional-design/domain-entities.md`
- `aidlc-docs/construction/u4-evaluation-harness/functional-design/business-logic-model.md`
- `aidlc-docs/construction/u4-evaluation-harness/functional-design/business-rules.md`

---

## Pre-Analysis Q&A

All answers derived from application design artifacts (application-design.md, unit-of-work.md, agent/models.py).

---

### Q1 — ExactMatchScorer: numeric comparison strategy

How should numeric answers be compared — strict equality, absolute tolerance, or relative tolerance?

**Options**:
- A) Absolute tolerance 1e-6 — floating-point equality
- B) Relative tolerance 1% — `abs(a-b)/max(abs(b), 1.0) <= 0.01`
- C) Two-pass: exact integer match first, then 1% relative for floats

**[Answer]: B** — Relative 1% tolerance handles real-world monetary and aggregate values where minor rounding differences exist across DB engines (e.g. FLOAT vs NUMERIC precision variants).

---

### Q2 — ExactMatchScorer: string normalization depth

How deep should string answer normalization go?

**Options**:
- A) Strip whitespace + lowercase only
- B) Strip whitespace + lowercase + remove punctuation
- C) Strip whitespace + lowercase + Unicode normalize (NFKC)

**[Answer]: A** — Strip + lowercase is sufficient; removing punctuation or Unicode-normalizing could produce false positives for string answers with meaningful punctuation (e.g. `"N/A"` vs `"NA"`).

---

### Q3 — LLMJudgeScorer: activation condition

When is the LLM judge called?

**Options**:
- A) Always — for every query regardless of ExactMatch result
- B) Waterfall — called only when ExactMatch FAILS
- C) Category-gated — only for queries tagged `category="COMPLEX"`

**[Answer]: B** — Waterfall minimizes LLM calls and cost; ExactMatch handles numeric and simple-string answers without LLM overhead.

---

### Q4 — BenchmarkRunner: concurrency model

How are HTTP calls to the agent issued?

**Options**:
- A) Sequential — one call at a time
- B) Limited concurrency — `asyncio.Semaphore(5)` (max 5 concurrent agent calls)
- C) Fully parallel — all trials fire simultaneously

**[Answer]: B** — `Semaphore(5)` limits agent load while keeping benchmark throughput reasonable.

---

### Q5 — pass@1 definition

What does pass@1 measure?

**Options**:
- A) Score of the first trial only
- B) Best-of-N (1.0 if any trial passes)
- C) Average across all N trials

**[Answer]: A** — pass@1 = first trial result only. Multiple trials (N) give a statistical estimate; the regression gate uses first-trial score to match standard LLM benchmark methodology.

---

### Q6 — RegressionSuite: tolerance gate

How strict is the regression gate?

**Options**:
- A) Zero tolerance — fail if `current < previous` (any drop)
- B) 2% grace — fail if `current < previous - 0.02`
- C) Configurable threshold from `settings`

**[Answer]: A** — Application design states "asserts pass@1 >= previous run" with no tolerance. Strict regression gate.

---

### Q7 — RegressionSuite: no baseline case

What happens when no previous run exists in score_log.jsonl?

**Options**:
- A) Auto-pass — `passed=True, delta=0.0, previous_score=0.0` (first run bootstraps baseline)
- B) Exception — must bootstrap explicitly before regression can run
- C) Special "bootstrapping" status returned

**[Answer]: A** — First run auto-passes with `previous_score=0.0`; no special bootstrapping step required.

---

### Q8 — QueryTraceRecorder: file layout

How are trace files organised under `results/traces/`?

**Options**:
- A) Flat — `results/traces/{query_id}_trial_{n}.json`
- B) Nested by run — `results/traces/{run_id}/{query_id}_trial_{n}.json`
- C) Single file per run — `results/traces/{run_id}.jsonl`

**[Answer]: B** — Nested by run_id keeps traces organized; allows inspecting any individual trial without scanning a single large file.

---

### Q9 — run_benchmark.py CLI: argument set

What arguments does the CLI expose?

**Options**:
- A) `--agent-url` only (trials defaults to 1, all queries run)
- B) `--agent-url`, `--trials` (default 1), `--category` filter
- C) `--agent-url`, `--trials` (default 1), `--queries-path` (optional), `--category` filter

**[Answer]: C** — Full CLI with optional filters mirrors BenchmarkWrapper API and allows targeted re-runs without modifying code.

---

### Q10 — LLMJudgeScorer: structured output format

How does the LLM judge return its verdict?

**Options**:
- A) Single JSON response: `{"passed": bool, "rationale": str, "confidence": float}`
- B) Two-step: first "PASS/FAIL", then "rationale"
- C) Template with rubric sections

**[Answer]: A** — Single JSON response maps directly to `JudgeVerdict` model; one LLM call per query minimizes cost and latency.

---

## Plan Steps

- [x] **Step 1** — Pre-analyze unit context and pre-fill all Q&A decisions
- [x] **Step 2** — Create `aidlc-docs/construction/u4-evaluation-harness/functional-design/domain-entities.md`
- [x] **Step 3** — Create `aidlc-docs/construction/u4-evaluation-harness/functional-design/business-logic-model.md`
- [x] **Step 4** — Create `aidlc-docs/construction/u4-evaluation-harness/functional-design/business-rules.md`
- [x] **Step 5** — Update aidlc-state.md and audit.md
