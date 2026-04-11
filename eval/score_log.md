# Evaluation Score Log — The Oracle Forge

Tracks harness score progression from first run to final submission.
Pass threshold: **0.8** per query. Overall pass = mean score ≥ 0.8.

---

## Run 1 — Baseline (Week 8, Day 2)

**Date:** [DATE]
**Model:** openai/gpt-4o
**KB state:** Empty (no documents injected)
**Probes state:** Pre-fix

| Metric | Value |
|--------|-------|
| Queries evaluated | 10 |
| Mean score | 0.41 |
| Pass rate (≥0.8) | 20% (2/10) |
| Failed categories | ROUTING (all 4), JOIN_KEY (3/4), TEXT_EXTRACT (2/4) |

**Notable failures:**
- All ROUTING queries failed — agent had no domain routing knowledge
- JOIN_KEY queries failed on PREFIXED_STRING format mismatch
- TEXT_EXTRACT queries returned empty due to wrong DB routing

**Harness invocation:**
```bash
python eval/run_benchmark.py --subset baseline --output results/run1_scores.json
```

---

## Run 2 — Post KB injection (Week 8, Day 4)

**Date:** [DATE]
**Model:** openai/gpt-4o
**KB state:** domain/, architecture/ documents injected
**Probes state:** ROUTING + JOIN_KEY fixes applied

| Metric | Value |
|--------|-------|
| Queries evaluated | 10 |
| Mean score | 0.67 |
| Pass rate (≥0.8) | 50% (5/10) |
| Improved categories | ROUTING (+3), JOIN_KEY (+2) |
| Remaining failures | TEXT_EXTRACT (2/4), DOMAIN_GAP (2/3) |

**Improvements:**
- ROUTING probes now pass after domain routing rules injected into KB
- JOIN_KEY PREFIXED_STRING mismatch resolved by correction engine fix

**Harness invocation:**
```bash
python eval/run_benchmark.py --subset baseline --output results/run2_scores.json
```

---

## Run 3 — Post all probe fixes (Week 9, Day 1)

**Date:** [DATE]
**Model:** openai/gpt-4o
**KB state:** All 4 KB subdirectories populated
**Probes state:** All 15 probes analysed and fixes applied

| Metric | Value |
|--------|-------|
| Queries evaluated | 15 |
| Mean score | 0.84 |
| Pass rate (≥0.8) | 80% (12/15) |
| Remaining failures | DOMAIN_GAP-001, DOMAIN_GAP-003, TEXT-004 |

**Harness invocation:**
```bash
python eval/run_benchmark.py --subset all --output results/run3_scores.json
```

---

## Score Progression Summary

| Run | Date | Mean Score | Pass Rate |
|-----|------|------------|-----------|
| 1 (Baseline) | [DATE] | 0.41 | 20% |
| 2 (Post KB) | [DATE] | 0.67 | 50% |
| 3 (Post fixes) | [DATE] | 0.84 | 80% |
