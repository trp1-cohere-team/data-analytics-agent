# Business Logic Model
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes  
**Note**: Technology-agnostic. No infrastructure or framework references.

---

## Module 1: JoinKeyUtils

### 1.1 Format Detection — `detect_format(key_samples)`

**Input**: `key_samples: list[Any]` — one or more sample values drawn from a key column  
**Output**: `JoinKeyFormatResult(primary_format, secondary_formats)`

**Algorithm**:

```
detect_format(key_samples):
  if len(key_samples) == 1:
    return JoinKeyFormatResult(
      primary_format = _classify_single(key_samples[0]),
      secondary_formats = []
    )

  # Multi-sample path: classify each, then vote
  classifications = [_classify_single(s) for s in key_samples]
  counts = frequency_count(classifications)
  primary = format with highest count (ties broken by format precedence: UUID > PREFIXED_STRING > COMPOSITE > INTEGER > UNKNOWN)
  secondary = all other formats that appeared at least once, excluding UNKNOWN, excluding primary
  return JoinKeyFormatResult(primary_format=primary, secondary_formats=secondary)
```

**Single-value classifier — `_classify_single(value)`**:

```
_classify_single(value):
  if value is Python int OR (value is str AND matches r'^\d+$'):
    return INTEGER

  if value is str AND matches r'^[A-Z][A-Z0-9]*-\d+$':
    return PREFIXED_STRING   # e.g. "CUST-01234", "ORD-007", "ITEM-9"

  if value is str AND matches r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$':
    return UUID

  if value is list OR value is tuple:
    return COMPOSITE

  if value is str AND (contains '|' OR contains '::'):
    return COMPOSITE

  return UNKNOWN
```

---

### 1.2 Key Value Transformation — `transform_key(value, source_fmt, target_fmt)`

**Input**: a key value, its detected source format, the required target format  
**Output**: the value converted to target format, or `None` if transformation is not defined

**Transformation table**:

| Source | Target | Rule |
|---|---|---|
| INTEGER | PREFIXED_STRING | Cannot determine prefix from value alone — returns `None`; caller must supply prefix via `build_transform_expression` |
| INTEGER | UUID | Not supported — returns `None` |
| PREFIXED_STRING | INTEGER | Strip prefix and hyphens; parse digits as int. E.g. "CUST-01234" → 1234 |
| PREFIXED_STRING | PREFIXED_STRING | Re-pad digits to target width if widths differ. E.g. "CUST-7" → "CUST-007" (if target width=3) |
| UUID | INTEGER | Not supported — returns `None` |
| COMPOSITE | Any | Not supported in value transform — use SQL expression only |

**Invariant**: `transform_key` is a pure function. Same inputs always produce same output. No side effects.

---

### 1.3 SQL Expression Builder — `build_transform_expression(source_column, source_fmt, target_fmt, db_type)`

**Input**: column reference (string), source format, target format, database dialect  
**Output**: SQL/MQL expression string that performs the transformation in-query

**Expression table by dialect**:

| Source→Target | PostgreSQL | SQLite | DuckDB | MongoDB (MQL) |
|---|---|---|---|---|
| INTEGER → PREFIXED_STRING | `CONCAT('{prefix}', LPAD(CAST({col} AS TEXT), {width}, '0'))` | `'{prefix}' \|\| printf('%0{width}d', {col})` | `CONCAT('{prefix}', LPAD(CAST({col} AS VARCHAR), {width}, '0'))` | `$concat: ['{prefix}', {$toString: {$substr: [{$toString:'${col}'}, 0, -1]}}]` |
| PREFIXED_STRING → INTEGER | `CAST(REGEXP_REPLACE({col}, '^[A-Z]+-', '') AS INTEGER)` | `CAST(SUBSTR({col}, INSTR({col},'-')+1) AS INTEGER)` | `CAST(REGEXP_REPLACE({col}, '^[A-Z]+-', '') AS INTEGER)` | `$toInt: {$arrayElemAt: [{$split:['${col}','-']}, -1]}` |

**Note**: `{prefix}` and `{width}` are resolved from JoinKeyFormatResult metadata or the domain KB join-key glossary before the expression is built. If they cannot be resolved, the expression cannot be built and the caller falls back to LLM correction.

---

## Module 2: MultiPassRetriever

### 2.1 Pass Query Generation — `_build_pass_queries(query)`

**Input**: the natural language query string  
**Output**: list of 3 keyword lists (one per pass)

**Pass definitions**:

```
Pass 1 — Failure vocabulary:
  Fixed high-value terms: ["syntax error", "join", "mismatch", "failed", "exception",
                           "wrong", "incorrect", "empty result", "null", "type error"]
  Augmented with: any DB-type names found in query (postgres, sqlite, mongodb, duckdb)

Pass 2 — Correction vocabulary:
  Fixed high-value terms: ["corrected", "fixed", "resolved", "rewritten", "rerouted",
                           "reformatted", "coalesce", "ifnull", "fallback", "retry"]
  Augmented with: failure type names if detected in query (syntax, join_key, data_quality)

Pass 3 — Domain vocabulary:
  Extracted from the query itself:
    - All nouns and noun phrases (heuristic: words > 4 chars, not stop words)
    - Any quoted strings in the query
    - Column/table name candidates (snake_case words, CamelCase words)
  These terms are matched against correction log's "original_query" and "corrected_query" fields
```

---

### 2.2 Retrieval and Scoring — `retrieve_corrections(query, corrections, passes=3)`

**Input**: query string, list of CorrectionEntry objects, number of passes  
**Output**: ranked list of up to 10 CorrectionEntry objects

**Algorithm**:

```
retrieve_corrections(query, corrections, passes=3):
  pass_queries = _build_pass_queries(query)         # list of 3 keyword lists
  corpus_size = len(corrections)
  use_idf = (corpus_size >= 20)

  # Compute IDF weights if corpus large enough
  if use_idf:
    doc_freq = {}
    for term in all_terms_across_all_passes:
      doc_freq[term] = count of corrections containing term
    idf = { term: log(corpus_size / (df + 1)) for term, df in doc_freq.items() }
  else:
    idf = {}   # all multipliers = 1.0

  # Score each correction entry
  scores = {}
  for entry in corrections:
    score = 0.0
    entry_text = entry.original_query + " " + entry.corrected_query + " " + entry.failure_type
    for pass_idx, keywords in enumerate(pass_queries):
      for keyword in keywords:
        if keyword.lower() in entry_text.lower():
          tier_score = _keyword_tier_score(keyword)   # 3 if high-value, 1 if low-value
          idf_multiplier = idf.get(keyword, 1.0) if use_idf else 1.0
          score += tier_score * idf_multiplier
    if score > 0:
      scores[entry.id] = (score, entry.timestamp, entry)

  # Sort: primary by score descending, tiebreaker by timestamp descending (recency)
  ranked = sorted(scores.values(), key=lambda x: (-x[0], -x[1]))
  return [entry for score, ts, entry in ranked[:10]]
```

**Keyword tier classification — `_keyword_tier_score(keyword)`**:

```
HIGH_VALUE_TERMS = {
  "join", "mismatch", "pipeline", "aggregate", "foreign key",
  "cust-", "composite", "uuid", "prefixed", "cross-db",
  "syntax error", "dialect", "reroute", "coalesce"
}

_keyword_tier_score(keyword):
  if any(high in keyword.lower() for high in HIGH_VALUE_TERMS):
    return 3
  return 1   # common/generic correction terms
```

---

## Module 3: SchemaIntrospector

### 3.1 Introspection Depth (Standard — Option B)

All 4 introspectors return a `DBSchema` with:
- Table/collection names
- Column names, data types, nullable flags
- Primary key column(s)
- Foreign key relationships (from_table.from_col → to_table.to_col)

### 3.2 Per-DB Introspection Logic

**PostgreSQL** — `introspect_postgres(db_name)`:
```
Query 1 (columns): SELECT table_name, column_name, data_type, is_nullable
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_catalog = db_name
  ORDER BY table_name, ordinal_position

Query 2 (primary keys): SELECT tc.table_name, kcu.column_name
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu ...
  WHERE tc.constraint_type = 'PRIMARY KEY'

Query 3 (foreign keys): SELECT tc.table_name, kcu.column_name,
    ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
  FROM information_schema.table_constraints tc ...
  WHERE tc.constraint_type = 'FOREIGN KEY'
```

**SQLite** — `introspect_sqlite(db_path)`:
```
Step 1: SELECT name FROM sqlite_master WHERE type='table'
Step 2: For each table: PRAGMA table_info({table}) → columns, types, nullable, pk flag
Step 3: For each table: PRAGMA foreign_key_list({table}) → FK relationships
```

**MongoDB** — `introspect_mongodb(db_name)`:
```
Step 1: list_collection_names()
Step 2: For each collection: sample 100 documents
Step 3: Union all field names and infer type from most common Python type seen
Step 4: No FK concept — FK field is empty for MongoDB schemas
Step 5: PK = '_id' for all collections (always present)
```

**DuckDB** — `introspect_duckdb(db_path)`:
```
Same query structure as PostgreSQL using DuckDB's information_schema
Plus: PRAGMA database_list to enumerate attached databases
```

### 3.3 Error Handling

```
On any MCP Toolbox call failure:
  - Log warning (do not raise)
  - Return DBSchema(db_name=db_name, tables=[], error="introspection_failed")
  - ContextManager receives partial SchemaContext and proceeds
  - Agent will note missing schema in LLM context (schema gap handled by KB domain docs)
```

---

## Module 4: BenchmarkWrapper

### 4.1 Simplified Benchmark API

Wraps `EvaluationHarness` with defaults suitable for developer use during construction:

```
run_subset(agent_url, query_ids, trials=5):
  queries = load_dab_queries(filter=query_ids)   # subset of full DAB set
  return EvaluationHarness.run_benchmark(agent_url, queries, n_trials=trials)

run_single(agent_url, query_id, trials=3):
  return run_subset(agent_url, [query_id], trials=trials)

run_category(agent_url, category, trials=5):
  queries = load_dab_queries(filter=lambda q: q.category == category)
  return run_subset(agent_url, [q.id for q in queries], trials=trials)
```

---

## Module 5: ProbeLibrary

### 5.1 ProbeRunner Execution Algorithm

```
run_probe(probe_entry, agent_url):
  # Pre-fix: run probe against live agent
  pre_response = HTTP POST agent_url/query {question: probe_entry.query}
  pre_fix_score = score_response(pre_response, probe_entry.expected_failure_mode)
  probe_entry.observed_agent_response = pre_response.answer
  probe_entry.pre_fix_score = pre_fix_score

  # Record failure signal
  probe_entry.error_signal = extract_error_signal(pre_response.query_trace)
  probe_entry.correction_attempt_count = count_correction_attempts(pre_response.query_trace)

  # Fix is applied manually (documented in probe entry) — ProbeRunner does not auto-apply
  # After fix, re-run:
  post_response = HTTP POST agent_url/query {question: probe_entry.query}
  post_fix_score = score_response(post_response, probe_entry.expected_failure_mode)
  probe_entry.post_fix_score = post_fix_score
  probe_entry.post_fix_pass = (post_fix_score >= 0.8)

  return probe_entry
```

### 5.2 Probe Categories (minimum 3 of 4 required)

| Category | ID | Description |
|---|---|---|
| Multi-DB routing failure | ROUTING | Agent queries wrong DB type; result is empty or wrong dialect error |
| Join key mismatch | JOIN_KEY | Cross-DB join fails because key formats differ (e.g. int vs "CUST-NNN") |
| Unstructured text extraction | TEXT_EXTRACT | Answer requires reading free-text field; LLM sub-call needed |
| Domain knowledge gap | DOMAIN_GAP | Agent lacks KB context to answer; must search domain KB before querying |

**Minimum coverage**: 4 probes for ROUTING, 4 probes for JOIN_KEY, 4 probes for TEXT_EXTRACT, 3 probes for DOMAIN_GAP = 15 total.
