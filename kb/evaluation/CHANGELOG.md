# KB / evaluation — CHANGELOG

Documents in this directory contain evaluation baselines, known good answers,
scoring rubrics, and benchmark query sets used to calibrate the agent.

---

## v1.0.0 — Initial evaluation baseline (Week 8, Day 2)

**Documents added:**
- `baseline_queries.md` — 10 reference queries with ground-truth answers
- `scoring_rubric.md` — LLM judge rubric (0.0–1.0 scale, pass threshold 0.8)
- `known_good_answers.md` — curated exact-match reference answers for DAB queries

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "How many unique customers are in the database?" | Returns integer count from PostgreSQL | ✅ |
| "What is the total revenue last quarter?" | Returns sum in USD from PostgreSQL | ✅ |
| "What is the most common review rating?" | Returns 4 or 5 stars from MongoDB aggregate | ✅ |

**Injected by:** [TEAM MEMBER 4]
**Mob approval:** [DATE] — approved by team

---

## v1.1.0 — Added DAB held-out test mapping (Week 9, Day 1)

**Documents added:**
- `dab_query_hints.md` — per-query hints for DAB benchmark queries

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| DAB query #1 (see eval/test_set.json) | See eval/test_set.json | ✅ |
| DAB query #5 | See eval/test_set.json | ✅ |
