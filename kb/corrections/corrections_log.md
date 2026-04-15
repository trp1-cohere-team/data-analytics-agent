# Corrections Log

Append-only log of recent stockmarket-specific corrections and fixes used to harden OracleForge.

---

### Correction - 2026-04-15T00:00:01Z
- **Session**: stockmarket-seed-001
- **Category**: schema
- **Error**: `duckdb.CatalogException: Table with name stock_prices does not exist`
- **Fix**: Replaced the assumed shared fact table with the correct DAB pattern: one DuckDB table per ticker symbol.
- **Retry**: 1
- **Outcome**: success - subsequent queries targeted ticker tables like `REAL` and `AAPL`

---

### Correction - 2026-04-15T00:00:02Z
- **Session**: stockmarket-seed-002
- **Category**: join-key
- **Error**: Generated SQL expected a `ticker` column inside DuckDB price tables
- **Fix**: Mapped `stockinfo.Symbol` to DuckDB table name and moved symbol resolution into the SQLite step.
- **Retry**: 1
- **Outcome**: success - cross-db workflow returned the expected security universe

---

### Correction - 2026-04-15T00:00:03Z
- **Session**: stockmarket-seed-003
- **Category**: syntax
- **Error**: `Binder Error: Referenced column Adj Close not found`
- **Fix**: Quoted the spaced identifier as `"Adj Close"` in DuckDB queries.
- **Retry**: 1
- **Outcome**: success - adjusted-close aggregations executed correctly

---

### Correction - 2026-04-15T00:00:04Z
- **Session**: stockmarket-seed-004
- **Category**: routing
- **Error**: Exchange and ETF filters were incorrectly applied in DuckDB instead of SQLite
- **Fix**: Moved `Listing Exchange`, `ETF`, `Market Category`, and `Financial Status` filtering into `stockinfo` and reserved DuckDB for OHLCV metrics.
- **Retry**: 1
- **Outcome**: success - security cohort selection matched dataset semantics

---

### Correction - 2026-04-15T00:00:05Z
- **Session**: stockmarket-seed-005
- **Category**: data-availability
- **Error**: Agent attempted to query symbols that were present in SQLite but missing as DuckDB tables
- **Fix**: Added a table-existence check through `information_schema.tables` before generating batch `UNION ALL` queries.
- **Retry**: 1
- **Outcome**: success - batch scans skipped missing tables and completed cleanly

---

### Correction - 2026-04-15T00:00:06Z
- **Session**: stockmarket-seed-006
- **Category**: semantic
- **Error**: Agent treated `Company Description` as a join key instead of a lookup field
- **Fix**: Restricted `Company Description` usage to ticker discovery and explanation only; all durable cross-db mapping now routes through `Symbol`.
- **Retry**: 1
- **Outcome**: success - metadata lookups no longer produced brittle joins

### Correction — 2026-04-15T11:32:06.322373+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.323461+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.324555+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.326468+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.327485+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.328497+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.330323+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.331325+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.332286+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.334301+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.335432+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.336498+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.338557+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.339557+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.343217+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.346305+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T11:32:06.347465+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T11:32:06.348238+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T11:32:06.374994+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in Financial Status
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1
