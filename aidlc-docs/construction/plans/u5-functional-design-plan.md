# U5 Functional Design Plan
# Unit 5 — Utilities & Adversarial Probes

**Status**: All answers received — generation in progress  
**Date**: 2026-04-11

---

## Plan Checkboxes

- [x] Answer functional design questions (below)
- [x] Generate business-logic-model.md — algorithms for JoinKeyUtils, MultiPassRetriever, SchemaIntrospector
- [x] Generate business-rules.md — validation rules, constraints, probe coverage requirements
- [x] Generate domain-entities.md — data structures: JoinKeyFormat, CorrectionEntry, SchemaContext, probe schema
- [x] Update plan checkboxes, aidlc-state.md, audit.md
- [x] Present completion message

---

## Context

U5 is built first (no unit dependencies). It contains pure utility functions called by U1 and U2. The algorithms below are genuinely underspecified at the application design level — these answers directly determine how the code behaves.

---

## Functional Design Questions

### Question 1: JoinKeyUtils — Format Detection Rules
`detect_format(key_sample: Any) → JoinKeyFormat` must return one of: `INTEGER | PREFIXED_STRING | UUID | COMPOSITE | UNKNOWN`.

What detection logic should it use? (Choose approach, then add any extra rules after [Answer]:)

A) Type-first, then pattern-match on a single sample value:
   - `INTEGER`: Python `int`, or string of only digits (no letters, no hyphens)
   - `PREFIXED_STRING`: string matching `^[A-Z]+-\d+$` (e.g. "CUST-01234", "ORD-007")
   - `UUID`: string matching standard UUID regex `^[0-9a-f]{8}-[0-9a-f]{4}-...$`
   - `COMPOSITE`: Python `tuple` or `list`, or string containing `|` or `::` separator
   - `UNKNOWN`: anything that doesn't match the above

B) Sample multiple values (up to 10) and vote — the format that wins majority is returned. Single sample falls back to A rules.

C) Other (describe after [Answer]: tag)

[Answer]: C — sample up to 10 values, return the majority format as primary_format but also return all detected minority formats as secondary_formats. Single sample falls back to A rules.

---

### Question 2: MultiPassRetriever — Ranking After 3 Passes
After running 3 vocabulary passes over the corrections log, `retrieve_corrections()` deduplicates and returns ranked results. How should ranking work?

A) Score = number of passes in which the entry matched (1–3). Ties broken by recency (most recent first). Return top 10.
B) Score = sum of keyword hits across all passes (each matching keyword +1). Return top 10.
C) No scoring — return union of all matches, deduplicated, sorted most-recent-first. Cap at 10.
D) Other (describe after [Answer]: tag)

[Answer]: D — weighted keyword scoring: rare/precise keywords score higher than common ones, recency as tiebreaker, cap at 10

---

### Question 3: SchemaIntrospector — Introspection Depth
`introspect_postgres/sqlite/mongodb/duckdb()` builds a `DBSchema`. What metadata should be captured?

A) Minimal — table/collection names, column names, column types only. (Fastest; fits in context easily)
B) Standard — table names, column names, column types, nullable flags, primary key columns, foreign key relationships. (Recommended for join key resolution)
C) Full — everything in B plus: indexes, unique constraints, sample 3 values per column (for join key format inference). (Most useful for LLM context; larger token footprint)
D) Other (describe after [Answer]: tag)

[Answer]: B 
---

### Question 4: ProbeLibrary — Probe Entry Schema
Each of the 15+ probes in `probes/probes.md` must document enough for the ProbeRunner to execute it and record results. What fields should each probe entry have?

A) Minimal: `id`, `category`, `query` (the adversarial NL question), `expected_failure_mode`, `fix_applied`, `post_fix_pass` (bool)
B) Standard (A + rationale): adds `description` (why this probe is adversarial), `observed_agent_response` (what the agent returned before fix), `pre_fix_score` (float), `post_fix_score` (float)
C) Full (B + reproduction): adds `db_types_involved`, `error_signal` (exact error text that triggered correction), `correction_attempt_count`
D) Other (describe after [Answer]: tag)

[Answer]: C 

---

---

## Follow-up Questions (ambiguities detected)

### Follow-up 1: Q1 — Interface Change for detect_format
Your answer (sample up to 10 values, return primary + secondary formats) changes two things from the component-methods.md signature:
- Input: `key_sample: Any` (single value) → needs to become a list or the caller must pass a list
- Return: `JoinKeyFormat` (single enum) → needs to become a richer type

Which approach?

A) Change signature to `detect_format(key_samples: list[Any]) -> JoinKeyFormatResult` where `JoinKeyFormatResult` is a dataclass with `primary_format: JoinKeyFormat` and `secondary_formats: list[JoinKeyFormat]`. Single-value callers pass a 1-element list.
B) Keep `detect_format(key_sample: Any) -> JoinKeyFormat` (single-sample, single-result) for all callers. Add a separate `detect_format_multi(key_samples: list[Any]) -> JoinKeyFormatResult` for the multi-sample path used only by JoinKeyResolver in U2.
C) Other (describe after [Answer]: tag)

[Answer]: A

---

### Follow-up 2: Q2 — Keyword Rarity Scoring
"Rare/precise keywords score higher than common ones" — on a 50-entry corrections log, how is rarity determined at runtime?

A) Static tier list — two fixed tiers defined in code:
   - High-value (score 3): domain-specific terms (e.g. "JOIN", "CUST-", "pipeline", "aggregate", column/table names extracted from query)
   - Low-value (score 1): common correction terms (e.g. "error", "failed", "wrong", "fix", "query")
   - Match score = sum of keyword tier scores across all passes
B) Dynamic IDF over the corrections corpus — compute term frequency across the 50 entries at retrieval time; rare terms (low doc frequency) get higher weight. IDF = log(N / df).
C) Other (describe after [Answer]: tag)

[Answer]: C — hybrid: static tiers as the stable baseline, IDF computed as a multiplier once the corpus reaches 20+ entries

---

Please fill in the [Answer]: tags above and let me know when done.
