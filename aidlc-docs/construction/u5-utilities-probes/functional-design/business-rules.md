# Business Rules
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## JoinKeyUtils Rules

### JKU-01: Detection Requires At Least One Sample
`detect_format` MUST receive a non-empty list. If called with an empty list, it MUST return `JoinKeyFormatResult(primary_format=UNKNOWN, secondary_formats=[])` — not raise an exception.

### JKU-02: Single-Sample Fallback
When `key_samples` has exactly one element, the multi-sample voting path MUST NOT be used. The single-value classifier `_classify_single` is applied directly and `secondary_formats` is always `[]`.

### JKU-03: Format Precedence on Ties
When two formats appear equally often in multi-sample detection, resolve ties by format precedence: `UUID > PREFIXED_STRING > COMPOSITE > INTEGER > UNKNOWN`. This rule ensures deterministic output for identical inputs.

### JKU-04: UNKNOWN Is Never a Secondary Format
`UNKNOWN` MUST NOT appear in `secondary_formats`. Secondary formats represent confirmed minority formats, not classification failures.

### JKU-05: transform_key Returns None on Unsupported Pairs
If a source→target transformation pair has no defined rule, `transform_key` MUST return `None`. It MUST NOT raise an exception. Callers check for `None` and fall back to LLM correction.

### JKU-06: build_transform_expression Requires Resolved Parameters
`build_transform_expression` MUST NOT generate an expression with unresolved placeholders (e.g. `{prefix}` still in the output string). If `{prefix}` or `{width}` cannot be resolved from context, the function MUST return `None`.

### JKU-07: Pure Functions — No Side Effects
All three JoinKeyUtils functions (`detect_format`, `transform_key`, `build_transform_expression`) MUST be pure: no global state mutation, no file I/O, no network calls. Same inputs always produce same outputs.

---

## MultiPassRetriever Rules

### MPR-01: Always Run All Passes
`retrieve_corrections` MUST always run all 3 passes regardless of early matches. Skipping passes to short-circuit would miss high-scoring entries in later passes.

### MPR-02: Deduplication Before Ranking
If the same `CorrectionEntry.id` appears in multiple passes, it MUST be counted once with the aggregated score (sum of all per-pass scores). Duplicate entries in the result list are not permitted.

### MPR-03: IDF Threshold Is Exactly 20 Entries
IDF multipliers MUST be applied when and only when `len(corrections) >= 20`. Below 20 entries, static tier scores are used with `idf_multiplier = 1.0` for all terms.

### MPR-04: Result Cap Is 10
The function MUST return at most 10 entries. If fewer than 10 entries match (score > 0), all matching entries are returned. If no entries match, an empty list is returned.

### MPR-05: Zero-Score Entries Excluded
Entries that match no keyword in any pass (score = 0) MUST NOT appear in results. Results contain only positive-scoring entries.

### MPR-06: Recency Tiebreaker Uses Timestamp
When two entries have equal scores, the one with the more recent `CorrectionEntry.timestamp` ranks higher. If timestamps are also equal, order is undefined (implementation-stable sort is acceptable).

### MPR-07: Pass Vocabulary Is Case-Insensitive
Keyword matching MUST be case-insensitive. "JOIN" and "join" and "Join" all match the same term.

---

## SchemaIntrospector Rules

### SI-01: Graceful Degradation on MCP Toolbox Failure
If the MCP Toolbox call for any DB introspection fails (network error, timeout, non-200 response), the introspector MUST return a `DBSchema` with empty tables and an `error` field set. It MUST NOT propagate the exception to the caller.

### SI-02: MongoDB Sampling Is Non-Deterministic — Results Must Be Stable
MongoDB introspection samples 100 documents. If a field appears in fewer than 10% of sampled documents, it MUST be included but marked `nullable=True`. The schema MUST reflect what was observed, not inferred.

### SI-03: introspect_all Succeeds Partially
`introspect_all` runs all 4 DB introspections. If one fails (per SI-01), the returned `SchemaContext` contains partial results — the failed DB has an empty schema. This MUST NOT cause `introspect_all` to fail.

### SI-04: Schema Is Read-Only
`SchemaIntrospector` functions MUST NOT write to, modify, or lock any database. All introspection is read-only SELECT / PRAGMA / sample queries.

---

## ProbeLibrary Rules

### PL-01: Minimum 15 Probes Required
`probes/probes.md` MUST contain at least 15 probe entries. Fewer than 15 probes is a validation failure (caught by the KB injection test).

### PL-02: Minimum 3 Failure Categories Required
At least 3 of the 4 defined failure categories (ROUTING, JOIN_KEY, TEXT_EXTRACT, DOMAIN_GAP) MUST be represented. Each represented category MUST have at least 3 probes.

### PL-03: Each Probe Entry Has All Required Fields
Every probe entry MUST contain all fields from the Full schema (Option C):
`id`, `category`, `query`, `expected_failure_mode`, `fix_applied`, `post_fix_pass`,
`description`, `observed_agent_response`, `pre_fix_score`, `post_fix_score`,
`db_types_involved`, `error_signal`, `correction_attempt_count`.
A probe without all fields MUST NOT be counted toward the minimum 15.

### PL-04: ProbeRunner Does Not Auto-Apply Fixes
`ProbeRunner` executes probes and records results. It MUST NOT automatically apply fixes to the agent's KB or corrections log. Fixes are documented in `fix_applied` field and applied manually. ProbeRunner then re-runs the probe to measure `post_fix_score`.

### PL-05: Probe IDs Are Unique
Each probe MUST have a unique `id`. Format: `{CATEGORY}-{NNN}` where NNN is zero-padded (e.g. `ROUTING-001`, `JOIN_KEY-003`).

### PL-06: post_fix_pass Threshold Is 0.8
A probe is considered "passing after fix" (`post_fix_pass = True`) when `post_fix_score >= 0.8`. This threshold is fixed and MUST NOT vary per probe.

---

## BenchmarkWrapper Rules

### BW-01: Wrapper Defaults to 5 Trials
`run_subset` and `run_category` default to `trials=5`. `run_single` defaults to `trials=3`. These are developer-use defaults (not the production 50-trial run).

### BW-02: Wrapper Delegates Fully to EvaluationHarness
`BenchmarkWrapper` MUST NOT implement its own scoring or trace recording. All logic is delegated to `EvaluationHarness`. The wrapper only provides simplified parameter defaults and query filtering.

---

## Cross-Module Rules

### U5-CROSS-01: No Unit Dependencies at Runtime
U5 functions MUST NOT import from U1, U2, U3, or U4. The only allowed imports are from `agent/models.py`, `agent/config.py`, and external libraries. Circular imports are a blocking build failure.

### U5-CROSS-02: All Functions Are Independently Testable
Every U5 function MUST be testable without a running MCP Toolbox, agent server, or database. Functions that require MCP Toolbox (SchemaIntrospector) MUST be designed with dependency injection so the HTTP client can be replaced with a mock in tests.
