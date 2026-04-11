# NFR Design Patterns
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## Pattern 1: Bulkhead Timeout (SchemaIntrospector)

**Addresses**: REL-U5-01, PERF-U5-02  
**Pattern**: Bulkhead + Timeout  
**Purpose**: Isolate each DB introspection so one slow DB cannot starve others; preserve all completed results on partial failure.

### Structure

```
introspect_all()
  │
  ├── outer: asyncio.timeout(9s)  ← hard ceiling, 1s margin below 10s NFR
  │
  └── asyncio.gather(return_exceptions=True)
        ├── asyncio.timeout(4.0s) → introspect_mongodb()
        ├── asyncio.timeout(2.5s) → introspect_postgres()
        ├── asyncio.timeout(1.5s) → introspect_duckdb()
        └── asyncio.timeout(1.0s) → introspect_sqlite()
```

### Timeout Budget

| DB | Sub-limit | Rationale |
|---|---|---|
| MongoDB | 4.0s | Document sampling (100 docs/collection) is I/O heavy |
| PostgreSQL | 2.5s | information_schema joins; moderate on large catalogs |
| DuckDB | 1.5s | Analytical engine; PRAGMA queries are fast |
| SQLite | 1.0s | Minimum floor; local file; PRAGMA is near-instant |
| **Sum** | **9.0s** | Fits within 9s outer ceiling |

### Behavior on Partial Failure

```
gather result = [DBSchema, TimeoutError, DBSchema, CancelledError]
                 postgres     mongodb       duckdb      sqlite
                 (ok)         (timed out)   (ok)        (cancelled by outer)

→ GracefulSchemaResult assembles:
  SchemaContext(databases={
    "postgres": DBSchema(tables=[...]),          # ok
    "mongodb":  DBSchema(tables=[], error="timeout_4.0s"),
    "duckdb":   DBSchema(tables=[...]),          # ok
    "sqlite":   DBSchema(tables=[], error="cancelled"),
  })
```

### Outer Ceiling Semantics
The outer `asyncio.timeout(9)` is a safety net for cases where all per-DB sub-limits somehow fail (e.g. implementation bug in a timeout wrapper). It guarantees the absolute worst-case startup delay is 9s. The 1s margin between 9s and the 10s NFR requirement allows for event loop scheduling latency.

---

## Pattern 2: None-Return Guard (JoinKeyUtils)

**Addresses**: JKU-05, JKU-06, REL-U5-02  
**Pattern**: Null Object / Sentinel Return  
**Purpose**: Prevent callers (U2 JoinKeyResolver, U1 Orchestrator) from receiving exceptions on unsupported transformation pairs. `None` is the explicit "not supported" signal.

### Structure

```
caller (JoinKeyResolver in U2):
  expr = build_transform_expression(col, src_fmt, tgt_fmt, db_type)
  if expr is None:
    # fall back to LLM correction — route to CorrectionEngine
    raise ExecutionFailure(type=JOIN_KEY_MISMATCH, ...)
  # otherwise: embed expr in SQL string
  query = f"SELECT {expr} AS normalized_key FROM ..."
```

### Unsupported Pair Table (returns None)

| Source | Target | Reason |
|---|---|---|
| INTEGER | UUID | No deterministic mapping |
| UUID | INTEGER | No deterministic mapping |
| UUID | PREFIXED_STRING | No deterministic mapping |
| COMPOSITE | Any | Composite keys require custom per-case logic |
| Any | COMPOSITE | Assembly of composite keys not supported |
| UNKNOWN | Any | Cannot transform what cannot be classified |

---

## Pattern 3: Hypothesis Invariant Registry (PBT)

**Addresses**: PBT-U5-01 through PBT-U5-05  
**Pattern**: Property Registry + Custom Strategy Factory  
**Purpose**: Organise all Hypothesis property tests in one place; make strategies reusable across test files.

### Strategy Factory (Custom Generators)

```
# tests/unit/strategies.py

@st.composite
def integer_keys(draw, min_val=1, max_val=999_999):
    """Generates valid INTEGER format key values."""
    return draw(st.integers(min_value=min_val, max_value=max_val))

@st.composite
def prefixed_keys(draw, prefix=None, width=None):
    """Generates valid PREFIXED_STRING format key values."""
    p = prefix or draw(st.sampled_from(["CUST", "ORD", "ITEM", "TXN"]))
    w = width or draw(st.integers(min_value=1, max_value=8))
    n = draw(st.integers(min_value=0, max_value=10**w - 1))
    return f"{p}-{str(n).zfill(w)}"

@st.composite
def uuid_keys(draw):
    """Generates valid UUID format key values."""
    return str(draw(st.uuids()))

@st.composite
def key_samples_with_majority(draw, primary_fmt, minority_fmts=None, n=None):
    """Generates a list of key samples where primary_fmt is the majority."""
    size = n or draw(st.integers(min_value=3, max_value=20))
    majority_count = size // 2 + 1
    minority_count = size - majority_count
    majority = [draw(strategy_for(primary_fmt)) for _ in range(majority_count)]
    minority = [draw(strategy_for(draw(st.sampled_from(minority_fmts or [JoinKeyFormat.INTEGER])))) for _ in range(minority_count)]
    return draw(st.permutations(majority + minority))
```

### Invariant Registry

| Property | Hypothesis Settings | Custom Strategy |
|---|---|---|
| PBT-U5-01 Round-trip | `max_examples=200, deadline=500ms` | `integer_keys`, `prefixed_keys` |
| PBT-U5-02 Output constraint | `max_examples=200, deadline=500ms` | same as above |
| PBT-U5-03 Idempotency | `max_examples=100, deadline=200ms` | same as above |
| PBT-U5-04 Monotonicity | `max_examples=100, deadline=500ms` | `key_samples_with_majority` |
| PBT-U5-05 Expression validity | `max_examples=150, deadline=200ms` | `integer_keys`, `prefixed_keys` + `st.sampled_from(["postgres","sqlite","duckdb","mongodb"])` |

### SQL Expression Validity Check (PBT-U5-05)

Lightweight validator — does not require a DB engine:

```
def is_valid_sql_expression(expr: str, source_column: str, db_type: str) -> bool:
    # Rule 1: no unresolved template placeholders
    assert '{' not in expr and '}' not in expr
    # Rule 2: source column name appears in expression
    assert source_column in expr
    # Rule 3: dialect-appropriate function names used
    if db_type == "sqlite":
        assert "LPAD" not in expr  # SQLite has no LPAD; uses printf
    if db_type in ("postgres", "duckdb"):
        assert "printf" not in expr  # postgres/duckdb use LPAD
    return True
```

---

## Pattern 4: Pass-Through Scorer (MultiPassRetriever)

**Addresses**: MPR-01 through MPR-07  
**Pattern**: Strategy + Accumulator  
**Purpose**: Each pass applies a different keyword vocabulary (strategy) over the corrections corpus; scores accumulate independently and are merged at the end.

### Structure

```
retrieve_corrections(query, corrections):
  pass_queries = _build_pass_queries(query)    # 3 keyword lists

  accumulator = {}   # entry_id → KeywordScore

  for pass_keywords in pass_queries:
    for entry in corrections:
      for keyword in pass_keywords:
        if match(keyword, entry):
          tier = _keyword_tier_score(keyword)   # 3 or 1
          idf  = _idf(keyword, corrections)     # 1.0 if corpus < 20
          accumulator[entry.id].raw_score += tier * idf

  ranked = sort(accumulator.values(), by=(-raw_score, -timestamp))
  return [e.entry for e in ranked[:10]]
```

### IDF Computation Gate

```
_idf(keyword, corrections):
  if len(corrections) < 20:
    return 1.0   # static tiers only
  df = count(c for c in corrections if keyword.lower() in c.searchable_text())
  return log(len(corrections) / (df + 1))   # +1 smoothing prevents div-by-zero
```
