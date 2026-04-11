# KB / corrections — CHANGELOG

Documents in this directory contain known failure patterns, correction recipes,
and post-fix validations derived from probe runs and live production errors.

---

## v1.0.0 — Initial corrections library (Week 8, Day 3)

**Documents added:**
- `syntax_corrections.md` — SQL dialect normalisations (ROWNUM→LIMIT, ISNULL→IS NULL, NVL→COALESCE)
- `join_key_corrections.md` — cross-DB join key format transforms (INTEGER↔PREFIXED_STRING↔UUID)
- `routing_corrections.md` — wrong-DB-type detection signals per database

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "Why did the query fail with ROWNUM?" | Rule: replace `WHERE ROWNUM <= N` with `LIMIT N` | ✅ |
| "Fix: ISNULL(col) returned syntax error" | Transform `ISNULL(col)` → `col IS NULL` | ✅ |
| "Join failed: type mismatch on customer_id" | Detect INTEGER vs PREFIXED_STRING; apply `LPAD(CAST(...))` | ✅ |

**Injected by:** [TEAM MEMBER 2]
**Mob approval:** [DATE] — approved by team

---

## v1.1.0 — Probe-driven correction additions (Week 8, Day 4)

**Documents added:**
- `probe_corrections.md` — corrections derived from running all 15 adversarial probes

**Fixes applied for probes:**
- ROUTING-001: Added domain KB rule — orders table lives only in PostgreSQL
- ROUTING-002: Added domain KB rule — sentiment_score is in DuckDB only
- JOIN-001: PREFIXED_STRING re-padding fix (`ORD-007` → `ORD-0007`)
- JOIN-002: INTEGER→PREFIXED_STRING LPAD transform
- TEXT-001: MongoDB `$text` search requires text index
- TEXT-002: DuckDB `LIKE` vs MongoDB `$regex` routing

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| Query routed to wrong DB (ROUTING-001) | Agent now routes to PostgreSQL | ✅ |
| Join key format mismatch (JOIN-001) | Agent applies PREFIXED_STRING re-pad | ✅ |
| Text search on non-indexed field (TEXT-001) | Agent falls back to MongoDB `$regex` | ✅ |

---

## v1.2.0 — LLM corrector post-analysis (Week 9, Day 1)

**Documents added:**
- `llm_correction_log.md` — cases where LLM corrector was invoked, with before/after queries

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "When does llm_correct run?" | Only when all 4 rule-based strategies fail | ✅ |
