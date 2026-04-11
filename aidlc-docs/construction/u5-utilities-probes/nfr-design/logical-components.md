# Logical Components
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## Component Map

```
U5 LOGICAL COMPONENTS

  SchemaIntrospector
    └── BulkheadTimeoutGather       ← manages outer + per-DB timeouts
    └── GracefulSchemaAssembler     ← converts gather results → SchemaContext

  JoinKeyUtils
    └── FormatClassifier            ← single-value _classify_single logic
    └── MajorityVoter               ← multi-sample voting with precedence rules
    └── TransformationRouter        ← dispatches to dialect-specific expression builders
    └── NullReturnGuard             ← wraps unsupported pairs → None (no exception)

  MultiPassRetriever
    └── PassVocabularyBuilder       ← generates 3 keyword lists from query
    └── ScoreAccumulator            ← per-entry weighted scoring with IDF gate
    └── ResultRanker                ← sort by score desc, timestamp desc; cap 10

  PBT Infrastructure
    └── StrategyFactory             ← custom Hypothesis @st.composite generators
    └── InvariantRegistry           ← maps property names to test functions + settings
    └── SqlExpressionValidator      ← lightweight dialect-aware expression checker
```

---

## Component 1: BulkheadTimeoutGather

**File**: `utils/schema_introspector.py` (internal to `introspect_all`)  
**Purpose**: Executes 4 DB introspections concurrently with independent per-DB timeouts and one outer safety ceiling.

### Interface

```python
async def _bulkhead_gather(tasks: dict[str, Coroutine], outer_timeout: float) -> dict[str, DBSchema | BaseException]:
    """
    Runs each coroutine in tasks with its own pre-configured timeout.
    Wraps the whole gather in outer_timeout as safety net.
    Returns dict of db_name → result (DBSchema or exception).
    """
```

### Timeout Configuration

```python
DB_TIMEOUTS: dict[str, float] = {
    "mongodb":  4.0,
    "postgres": 2.5,
    "duckdb":   1.5,
    "sqlite":   1.0,
}
OUTER_TIMEOUT: float = 9.0  # 1s margin below 10s NFR ceiling
```

### Behaviour

- Each task is wrapped: `asyncio.wait_for(coro, timeout=DB_TIMEOUTS[db_name])`
- All wrapped tasks collected into `asyncio.gather(..., return_exceptions=True)`
- Outer `asyncio.timeout(OUTER_TIMEOUT)` wraps the gather call
- On per-DB timeout: `asyncio.TimeoutError` captured as result for that DB
- On outer timeout: remaining incomplete tasks cancelled; completed results preserved via `return_exceptions=True`

---

## Component 2: GracefulSchemaAssembler

**File**: `utils/schema_introspector.py` (internal to `introspect_all`)  
**Purpose**: Converts the raw gather output (mix of `DBSchema` results and exceptions) into a coherent `SchemaContext`.

### Interface

```python
def _assemble_schema(results: dict[str, DBSchema | BaseException]) -> SchemaContext:
    """
    For each result:
      - DBSchema instance → include as-is
      - Exception → create empty DBSchema with error field set
    Returns SchemaContext with all 4 DBs represented (some may be empty).
    """
```

### Error Field Mapping

| Exception Type | `DBSchema.error` Value |
|---|---|
| `asyncio.TimeoutError` | `"timeout_{N}s"` (e.g. `"timeout_4.0s"`) |
| `asyncio.CancelledError` | `"cancelled"` |
| `aiohttp.ClientError` | `"connection_error: {msg}"` |
| Any other exception | `"introspection_error: {type}"` |

---

## Component 3: FormatClassifier

**File**: `utils/join_key_utils.py` (internal function `_classify_single`)  
**Purpose**: Classifies one key value into a `JoinKeyFormat` using type checks and compiled regex patterns.

### Compiled Patterns (module-level constants)

```python
_DIGITS_RE   = re.compile(r'^\d+$')
_PREFIXED_RE = re.compile(r'^[A-Z][A-Z0-9]*-\d+$')
_UUID_RE     = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
```

### Decision Tree

```
isinstance(value, int)           → INTEGER
isinstance(value, (list, tuple)) → COMPOSITE
isinstance(value, str):
  _DIGITS_RE.match(value)        → INTEGER
  _PREFIXED_RE.match(value)      → PREFIXED_STRING
  _UUID_RE.match(value)          → UUID
  '|' in value or '::' in value  → COMPOSITE
  else                           → UNKNOWN
else (float, None, dict, …)      → UNKNOWN
```

---

## Component 4: MajorityVoter

**File**: `utils/join_key_utils.py` (internal to `detect_format`)  
**Purpose**: Votes on format across multiple samples; applies precedence rule on ties; separates primary from secondary formats.

### Precedence Order (for tie-breaking)

```
UUID > PREFIXED_STRING > COMPOSITE > INTEGER > UNKNOWN
```

### Algorithm

```
counts = Counter(_classify_single(s) for s in key_samples)
# Remove UNKNOWN from voting (it can't win primary)
counts.pop(UNKNOWN, None)

if not counts:
    return JoinKeyFormatResult(primary_format=UNKNOWN, secondary_formats=[])

# Find max count; apply precedence on tie
max_count = max(counts.values())
candidates = [fmt for fmt, cnt in counts.items() if cnt == max_count]
primary = max(candidates, key=lambda f: PRECEDENCE[f])

secondary = [fmt for fmt in counts if fmt != primary]
return JoinKeyFormatResult(primary_format=primary, secondary_formats=secondary)
```

---

## Component 5: NullReturnGuard

**File**: `utils/join_key_utils.py` (wrapper logic in `transform_key` and `build_transform_expression`)  
**Purpose**: Ensures unsupported transformation pairs return `None` rather than raising exceptions. Implemented as an early-return check before any transformation logic.

### Guard Table (checked at function entry)

```python
UNSUPPORTED_TRANSFORMS: set[tuple[JoinKeyFormat, JoinKeyFormat]] = {
    (INTEGER,          UUID),
    (UUID,             INTEGER),
    (UUID,             PREFIXED_STRING),
    (PREFIXED_STRING,  UUID),
    (COMPOSITE,        INTEGER),
    (COMPOSITE,        PREFIXED_STRING),
    (COMPOSITE,        UUID),
    (INTEGER,          COMPOSITE),
    (PREFIXED_STRING,  COMPOSITE),
    (UNKNOWN,          INTEGER),
    (UNKNOWN,          PREFIXED_STRING),
    (UNKNOWN,          UUID),
    (UNKNOWN,          COMPOSITE),
}

def transform_key(value, source_fmt, target_fmt):
    if (source_fmt, target_fmt) in UNSUPPORTED_TRANSFORMS:
        return None
    if source_fmt == target_fmt:
        return value   # identity
    # ... transformation logic ...
```

---

## Component 6: PassVocabularyBuilder

**File**: `utils/multi_pass_retriever.py` (function `_build_pass_queries`)  
**Purpose**: Generates 3 distinct keyword lists from the input query — one per vocabulary domain.

### Fixed Vocabulary Sets

```python
PASS1_BASE = frozenset([
    "syntax error", "join", "mismatch", "failed", "exception",
    "wrong", "incorrect", "empty result", "null", "type error",
    "postgres", "sqlite", "mongodb", "duckdb",
])

PASS2_BASE = frozenset([
    "corrected", "fixed", "resolved", "rewritten", "rerouted",
    "reformatted", "coalesce", "ifnull", "fallback", "retry",
    "syntax", "join_key", "data_quality",
])

STOP_WORDS = frozenset(["the", "a", "an", "is", "are", "was", "were",
                         "for", "of", "in", "on", "at", "to", "from"])
```

### Pass 3 Domain Term Extraction

```
domain_terms = {
  word for word in query.split()
  if len(word) > 4
  and word.lower() not in STOP_WORDS
  and not word.isdigit()
}
# Also include any snake_case tokens (likely column/table names)
snake_case_terms = re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', query)
domain_terms |= set(snake_case_terms)
```

---

## Component 7: ScoreAccumulator

**File**: `utils/multi_pass_retriever.py` (internal to `retrieve_corrections`)  
**Purpose**: Accumulates per-entry scores across all 3 passes using static tiers and optional IDF multipliers.

### IDF Gate

```python
def _compute_idf(corrections: list[CorrectionEntry]) -> dict[str, float]:
    if len(corrections) < 20:
        return {}   # empty → all IDF multipliers default to 1.0
    N = len(corrections)
    df = Counter()
    for entry in corrections:
        text = entry.original_query + " " + (entry.corrected_query or "")
        for term in set(text.lower().split()):
            df[term] += 1
    return {term: math.log(N / (count + 1)) for term, count in df.items()}
```

### Scoring

```python
idf_table = _compute_idf(corrections)
scores: dict[str, KeywordScore] = {}

for entry in corrections:
    text = (entry.original_query + " " + (entry.corrected_query or "") +
            " " + entry.failure_type).lower()
    for keywords in pass_queries:
        for kw in keywords:
            if kw.lower() in text:
                tier = 3 if any(h in kw.lower() for h in HIGH_VALUE_TERMS) else 1
                idf  = idf_table.get(kw.lower(), 1.0)
                if entry.id not in scores:
                    scores[entry.id] = KeywordScore(entry.id, 0.0, entry.timestamp, entry)
                scores[entry.id].raw_score += tier * idf
```

---

## Component 8: StrategyFactory + InvariantRegistry

**File**: `tests/unit/strategies.py`  
**Purpose**: Centralises all custom Hypothesis strategies so test files import from one place. InvariantRegistry maps property IDs to Hypothesis settings.

### Registry

```python
INVARIANT_SETTINGS = {
    "PBT-U5-01": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-02": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-03": settings(max_examples=100, deadline=timedelta(milliseconds=200)),
    "PBT-U5-04": settings(max_examples=100, deadline=timedelta(milliseconds=500)),
    "PBT-U5-05": settings(max_examples=150, deadline=timedelta(milliseconds=200)),
}
```

### SqlExpressionValidator

```python
def validate_sql_expression(expr: str, source_column: str, db_type: str) -> bool:
    """Lightweight structural check — no DB engine required."""
    assert '{' not in expr, f"Unresolved placeholder in: {expr}"
    assert source_column in expr, f"Source column missing from: {expr}"
    if db_type == "sqlite":
        assert "LPAD" not in expr, "SQLite: use printf, not LPAD"
    if db_type in ("postgres", "duckdb"):
        assert "printf" not in expr, "postgres/duckdb: use LPAD, not printf"
    return True
```

---

## Component Dependency Map (U5 Internal)

```
introspect_all()
  └── BulkheadTimeoutGather
        └── GracefulSchemaAssembler

detect_format()
  └── MajorityVoter
        └── FormatClassifier

transform_key()
  └── NullReturnGuard

build_transform_expression()
  └── NullReturnGuard
  └── TransformationRouter (dialect dispatch table)

retrieve_corrections()
  └── PassVocabularyBuilder
  └── ScoreAccumulator
        └── IDF Gate
  └── ResultRanker

[tests]
  └── StrategyFactory
  └── InvariantRegistry
  └── SqlExpressionValidator
```
