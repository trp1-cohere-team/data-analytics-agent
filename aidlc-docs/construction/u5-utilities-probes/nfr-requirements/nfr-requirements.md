# NFR Requirements
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## NFR Category Status

| Category | Status | Rationale |
|---|---|---|
| Scalability | N/A | Pure utility functions; no server, no concurrency management |
| Availability | N/A | No standalone process; runs inside U1/U2 process lifecycle |
| Security | N/A | No user input, no secrets, no network auth; MCP Toolbox is localhost only |
| Usability | N/A | Library code — no UI or end-user API |
| Performance | Partial | No per-call budget on JoinKeyUtils; explicit timeout on SchemaIntrospector startup |
| Reliability | Required | Graceful degradation on MCP Toolbox failure; no cascading errors |
| Maintainability | Required | Pure functions; full test coverage; PBT for core utilities |
| PBT Extension | **BLOCKING** | Full invariant suite required for JoinKeyUtils |

---

## Performance Requirements

### PERF-U5-01: JoinKeyUtils — No Enforced Per-Call Budget
`detect_format`, `transform_key`, and `build_transform_expression` have no enforced latency threshold. They are pure in-memory functions with O(1) complexity and will not be monitored for latency. Code must remain simple and direct — no caching, memoization, or optimization beyond straightforward implementation.

### PERF-U5-02: SchemaIntrospector — 10-Second Total Startup Timeout
`introspect_all()` must complete within **10 seconds total** across all 4 DB introspections. If MCP Toolbox does not respond within the budget:
- The introspector aborts remaining calls
- Returns a partial `SchemaContext` (DBs that completed are included; timed-out DBs have empty schema with `error` field set)
- Server startup proceeds with whatever schema was obtained
- Timeout is enforced using `asyncio.wait_for` with timeout=10 on the `asyncio.gather` call

### PERF-U5-03: MultiPassRetriever — Bounded by Corpus Size
`retrieve_corrections` complexity is O(P × K × N) where P=3 passes, K=keywords per pass, N=50 max corrections. No explicit latency requirement; acceptable latency is inherently bounded by the fixed corpus limit.

---

## Reliability Requirements

### REL-U5-01: SchemaIntrospector Never Blocks Server Startup
Server startup MUST NOT fail due to MCP Toolbox being unavailable. The 10-second timeout (PERF-U5-02) ensures the server is always reachable within 10 seconds of process start, regardless of MCP Toolbox state.

### REL-U5-02: JoinKeyUtils Returns None, Never Raises
`transform_key` and `build_transform_expression` MUST return `None` for unsupported combinations instead of raising exceptions. Callers (U2 JoinKeyResolver) check for `None` and handle gracefully. This is already enforced by JKU-05 and JKU-06 in business-rules.md.

### REL-U5-03: detect_format Returns UNKNOWN, Never Raises
`detect_format` MUST return `JoinKeyFormatResult(primary_format=UNKNOWN, secondary_formats=[])` for unclassifiable inputs, including empty lists, instead of raising. Enforced by JKU-01.

### REL-U5-04: ProbeRunner Does Not Affect Agent State
`ProbeRunner` MUST be a read-only observer — it calls the agent via HTTP and records results but MUST NOT write to `kb/corrections/`, `agent/memory/`, or any agent-internal state. The agent itself may update its own corrections during probe execution; that is expected and acceptable.

---

## Maintainability Requirements

### MAINT-U5-01: Unit Test Coverage ≥ 90% for JoinKeyUtils and MultiPassRetriever
These are pure functions — 90% line coverage is achievable. Code generation must include tests for:
- All detection format paths in `_classify_single`
- All transformation pairs (defined + unsupported returning `None`)
- All 3 pass vocabulary build paths
- IDF enabled (≥20 entries) and disabled (<20 entries) paths
- Scoring tiebreaker by recency

### MAINT-U5-02: SchemaIntrospector Uses Dependency-Injected HTTP Client
The MCP Toolbox HTTP client MUST be injected (not hardcoded) so tests can pass a mock client without a real MCP Toolbox process. This is required for `test_schema_introspector.py` to run in isolation.

### MAINT-U5-03: All U5 Functions Have Docstrings
Every public function in U5 MUST have a docstring stating: inputs, outputs, and key invariants. This is the primary documentation source — no separate API docs are generated.

---

## Property-Based Testing Requirements (BLOCKING Extension)

PBT applies to U5 with the **full invariant suite** (Option C). All properties below MUST be implemented using the `hypothesis` library. Failure to implement any property is a blocking finding.

### PBT-U5-01: Round-Trip Property (transform_key)
For every supported source→target format pair (PREFIXED_STRING→INTEGER, INTEGER→PREFIXED_STRING where prefix is known, PREFIXED_STRING→PREFIXED_STRING with different widths):

```
∀ v in valid_key_values(source_fmt):
  reverse = transform_key(transform_key(v, source_fmt, target_fmt), target_fmt, source_fmt)
  assert reverse == v  (or equivalent within numeric precision)
```

Hypothesis strategy: generate valid key values per format using custom `@st.composite` strategies.

### PBT-U5-02: Output Constraint Property (transform_key + detect_format)
For any value produced by `transform_key`, detecting its format must confirm it matches the target:

```
∀ v in valid_key_values(source_fmt), (source_fmt, target_fmt) in supported_pairs:
  result = transform_key(v, source_fmt, target_fmt)
  if result is not None:
    detected = detect_format([result])
    assert detected.primary_format == target_fmt
```

### PBT-U5-03: Idempotency Property (transform_key)
Applying the same transformation twice must yield the same result as applying it once:

```
∀ v, source_fmt, target_fmt:
  first = transform_key(v, source_fmt, target_fmt)
  second = transform_key(first, source_fmt, target_fmt) if first is not None else None
  assert first == second
```

### PBT-U5-04: Monotonicity Property (detect_format)
For N samples with a clear majority format, any majority-sized subset must give the same primary format:

```
∀ samples: list[Any] where len(samples) >= 3 and one format appears > 50%:
  full_result = detect_format(samples)
  majority_subset = [s for s in samples if _classify_single(s) == full_result.primary_format]
  subset_result = detect_format(majority_subset)
  assert subset_result.primary_format == full_result.primary_format
```

### PBT-U5-05: Expression Validity Property (build_transform_expression)
Every non-None SQL expression returned by `build_transform_expression` must be parseable as valid SQL for its stated dialect:

```
∀ source_column, source_fmt, target_fmt, db_type in valid_combinations:
  expr = build_transform_expression(source_column, source_fmt, target_fmt, db_type)
  if expr is not None:
    assert is_valid_sql(expr, dialect=db_type)  # lightweight regex/parse check
    assert source_column in expr  # column reference preserved
    assert '{' not in expr  # no unresolved template placeholders
```

`is_valid_sql` check: verify no unresolved `{placeholder}` syntax and basic SQL token structure (no assertion of full parse validity, which would require a DB engine).

---

## PBT Extension Compliance Summary

| Rule | Status | Notes |
|---|---|---|
| Hypothesis framework used | Required | Import `hypothesis` + `hypothesis.strategies` |
| Custom value generators | Required | `@st.composite` strategies per JoinKeyFormat |
| Round-trip test | PBT-U5-01 | Blocking |
| Output constraint test | PBT-U5-02 | Blocking |
| Idempotency test | PBT-U5-03 | Blocking |
| Monotonicity test | PBT-U5-04 | Blocking |
| Expression validity test | PBT-U5-05 | Blocking |
| MultiPassRetriever invariants | Required | Score is always ≥ 0 for matching entries; result count ≤ 10 |
