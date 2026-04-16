# Corrections Log

Append-only log of recent stockmarket-specific corrections and fixes used to harden OracleForge.

---

### Correction - 2026-04-14T23:40:00Z
- **Session**: seed-postgres-agg
- **Category**: query
- **Error**: `column "avg_rating" does not exist` in PostgreSQL aggregation query
- **Fix**: Replaced alias misuse with explicit `AVG(rating_number)` projection and grouped by canonical key columns.
- **Retry**: 1
- **Outcome**: success - aggregation query returned expected grouped rows

---

### Correction - 2026-04-14T23:45:00Z
- **Session**: seed-mongo-field-access
- **Category**: query
- **Error**: Mongo aggregation used flat `genre` field while data is nested under `genre.name`
- **Fix**: Updated pipeline to reference nested path and added explicit `$project` before `$group`.
- **Retry**: 1
- **Outcome**: success - genre rollups returned valid counts

---

### Correction - 2026-04-14T23:50:00Z
- **Session**: seed-duckdb-lateral
- **Category**: query
- **Error**: DuckDB query failed on array expansion due to missing LATERAL semantics
- **Fix**: Rewrote query using `CROSS JOIN LATERAL UNNEST(...)` with proper aliasing.
- **Retry**: 1
- **Outcome**: success - unstructured field expansion produced expected rows

---

### Correction - 2026-04-15T00:00:01Z
- **Session**: stockmarket-seed-001
- **Category**: query
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
- **Category**: query
- **Error**: `Binder Error: Referenced column Adj Close not found`
- **Fix**: Quoted the spaced identifier as `"Adj Close"` in DuckDB queries.
- **Retry**: 1
- **Outcome**: success - adjusted-close aggregations executed correctly

---

### Correction - 2026-04-15T00:00:04Z
- **Session**: stockmarket-seed-004
- **Category**: db-type
- **Error**: Exchange and ETF filters were incorrectly applied in DuckDB instead of SQLite
- **Fix**: Moved `Listing Exchange`, `ETF`, `Market Category`, and `Financial Status` filtering into `stockinfo` and reserved DuckDB for OHLCV metrics.
- **Retry**: 1
- **Outcome**: success - security cohort selection matched dataset semantics

---

### Correction - 2026-04-15T00:00:05Z
- **Session**: stockmarket-seed-005
- **Category**: data-quality
- **Error**: Agent attempted to query symbols that were present in SQLite but missing as DuckDB tables
- **Fix**: Added a table-existence check through `information_schema.tables` before generating batch `UNION ALL` queries.
- **Retry**: 1
- **Outcome**: success - batch scans skipped missing tables and completed cleanly

---

### Correction - 2026-04-15T00:00:06Z
- **Session**: stockmarket-seed-006
- **Category**: join-key
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

### Correction — 2026-04-15T16:14:20.636002+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.636177+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.636326+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.636570+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.636718+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.636852+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.637126+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.637262+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.637391+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.637630+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.637759+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.637889+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.638149+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.638284+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.638417+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.638697+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:14:20.638837+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:14:20.638991+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:14:20.644986+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.002861+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.003046+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.003187+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.003436+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.003574+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.003705+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.003960+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.004107+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.004244+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.004487+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.004623+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.004754+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.005624+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.005840+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.006021+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.006285+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:37:59.006421+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:37:59.006555+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:37:59.013602+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.751890+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.752128+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.752314+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.752717+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.752912+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.753117+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.753434+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.753616+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.753792+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.754145+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.754331+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.754514+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.754832+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.755029+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.755215+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.755537+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:38:08.755719+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:38:08.755902+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:38:08.762169+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.840994+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.841159+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.841304+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.841559+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.841696+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.841834+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.842099+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.842301+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.842452+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.842707+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.842839+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.843000+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.843251+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.843381+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.843514+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.843752+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T16:50:27.843883+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T16:50:27.844040+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T16:50:27.850586+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.751969+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.752139+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.752278+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.752524+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.752660+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.752792+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.753076+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.753214+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.753346+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.753592+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.753724+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.753856+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.754122+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.754256+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.754388+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.754640+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:09:56.754775+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:09:56.754905+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:09:56.762080+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.657844+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.658044+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.658203+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.658469+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.658620+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.658766+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.659053+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.659202+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.659344+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.659608+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.659751+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.659893+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.660185+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.660334+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.660476+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.660730+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-15T17:29:37.660891+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-15T17:29:37.661062+00:00
- **Session**: probe-mg
- **Category**: query
- **Error**: simulated persistent failure
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-15T17:29:37.668579+00:00
- **Session**: probe-mg
- **Category**: data-quality
- **Error**: null values in required column
- **Fix**: Verify that the expected data exists, check data formats and encoding.
- **Retry**: 1

### Correction — 2026-04-16T00:57:42.924604+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 1

### Correction — 2026-04-16T00:57:44.541323+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 2

### Correction — 2026-04-16T00:57:46.086330+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 3

### Correction — 2026-04-16T00:57:52.250699+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: invalid_code_payload
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 1

### Correction — 2026-04-16T00:57:53.596927+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: invalid_code_payload
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 2

### Correction — 2026-04-16T00:57:54.919119+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 3

### Correction — 2026-04-16T00:57:58.800884+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 1

### Correction — 2026-04-16T00:58:00.372142+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 2

### Correction — 2026-04-16T00:58:01.513782+00:00
- **Session**: 0d881093-64e6-4190-8237-5a50901401c2
- **Category**: db-type
- **Error**: unknown_tool: <STR> not in registry
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 3

### Correction — 2026-04-16T01:05:28.051564+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Binder Error: column "Date" must appear in the GROUP BY clause or must be part of an aggregate function.
Either add it to the GROUP BY list, or use "ANY_VALUE(Date)" if the exact value of...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:05:31.339563+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Symbol" not found in FROM clause!
Candidate bindings: "Close"

LINE <NUM>: ...geVolume, Symbol FROM FTR WHERE Date LIKE <STR> GROUP BY Symbol
              ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T01:05:35.961923+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: db-type
- **Error**: bridge_error: <NUM> Client Error: BAD REQUEST for url: http://localhost:<NUM>/invoke
- **Fix**: Verify the correct database tool is selected and the service is available.
- **Retry**: 3

### Correction — 2026-04-16T01:05:39.656838+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Volume" not found in FROM clause!
Candidate bindings: "table_type", "table_schema"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM informati...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:05:42.524832+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Parser Error: syntax error at or near "Status"

LINE <NUM>: ...Volume FROM (SELECT Symbol FROM stockinfo WHERE `Financial Status` IN (<STR>, <STR>) AND `Nasdaq Traded` = <STR>) AS s JOIN...
       ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:05:44.219667+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Parser Error: syntax error at or near "Status"

LINE <NUM>: ...Volume FROM (SELECT Symbol FROM stockinfo WHERE `Financial Status` IN (<STR>, <STR>) AND `Nasdaq Traded` = <STR>) AS s JOIN...
       ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T01:05:46.022010+00:00
- **Session**: 7af53622-225f-4018-a5c9-a35b7da071c2
- **Category**: query
- **Error**: query_error: Parser Error: syntax error at or near "Status"

LINE <NUM>: ... table_name IN (SELECT Symbol FROM stockinfo WHERE `Financial Status` IN (<STR>, <STR>) AND `Nasdaq Traded` = <STR>)
                 ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-16T01:08:06.713836+00:00
- **Session**: 61d5c99f-f2cf-4207-aa72-642dedc3af80
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Volume" not found in FROM clause!
Candidate bindings: "table_type", "table_schema"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM informati...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:08:08.111739+00:00
- **Session**: 61d5c99f-f2cf-4207-aa72-642dedc3af80
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Volume" not found in FROM clause!
Candidate bindings: "table_type", "table_schema"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM informati...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T01:08:13.879258+00:00
- **Session**: 61d5c99f-f2cf-4207-aa72-642dedc3af80
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:10:27.921790+00:00
- **Session**: ef40d449-3b82-4e98-8492-a89c82823b25
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Volume" not found in FROM clause!
Candidate bindings: "table_type", "table_schema"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM informati...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:10:30.838424+00:00
- **Session**: ef40d449-3b82-4e98-8492-a89c82823b25
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "Volume" not found in FROM clause!
Candidate bindings: "table_type", "table_schema"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT *...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T01:10:40.298107+00:00
- **Session**: ef40d449-3b82-4e98-8492-a89c82823b25
- **Category**: query
- **Error**: query_error: Parser Error: syntax error at or near "Status"

LINE <NUM>: SELECT Symbol FROM stockinfo WHERE `Financial Status` IN (<STR>, <STR>, <STR>) AND `Nasdaq Traded` = <STR>
                                ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:14:47.326252+00:00
- **Session**: bc407e9d-0a39-4fdb-bf3e-9e4f6bce2295
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T01:14:52.583970+00:00
- **Session**: bc407e9d-0a39-4fdb-bf3e-9e4f6bce2295
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT * ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T01:14:55.024594+00:00
- **Session**: bc407e9d-0a39-4fdb-bf3e-9e4f6bce2295
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT * ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-16T02:34:47.684576+00:00
- **Session**: 6f060848-5301-4cb5-b91d-8f436ccbd4e7
- **Category**: query
- **Error**: query_error: Catalog Error: Table with name AAPL does not exist!
Did you mean "ADAP"?

LINE <NUM>: SELECT AVG("Close") FROM AAPL
                                 ^
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:34:52.418392+00:00
- **Session**: 6f060848-5301-4cb5-b91d-8f436ccbd4e7
- **Category**: query
- **Error**: query_error: Catalog Error: Table with name AAPL does not exist!
Did you mean "ADAP"?

LINE <NUM>: SELECT COUNT(*) FROM AAPL
                             ^
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:36:58.033213+00:00
- **Session**: 6fc44106-97a9-453d-8614-998a6046a1ea
- **Category**: query
- **Error**: query_error: Catalog Error: Table with name AAPL does not exist!
Did you mean "ADAP"?

LINE <NUM>: SELECT AVG("Close") FROM AAPL
                                 ^
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:42:27.782514+00:00
- **Session**: cabd5f05-4494-46ed-8b58-54f7fce21cae
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:42:29.517318+00:00
- **Session**: cabd5f05-4494-46ed-8b58-54f7fce21cae
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT * ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T02:43:03.745113+00:00
- **Session**: 3782105f-1083-48b0-9235-a204ff6ea6be
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:43:05.406922+00:00
- **Session**: 3782105f-1083-48b0-9235-a204ff6ea6be
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT * ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T02:43:07.153130+00:00
- **Session**: 3782105f-1083-48b0-9235-a204ff6ea6be
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: SELECT AVG(Volume) AS AverageVolume, table_name FROM (SELECT * ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 3

### Correction — 2026-04-16T02:44:17.961268+00:00
- **Session**: 39c32773-6ad2-4b05-8620-cafc7a594ba8
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:45:22.405363+00:00
- **Session**: 2c1f8bf7-f3ee-4086-aa51-a0ea9a537fc8
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1

### Correction — 2026-04-16T02:45:24.284918+00:00
- **Session**: 2c1f8bf7-f3ee-4086-aa51-a0ea9a537fc8
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 2

### Correction — 2026-04-16T02:46:05.266703+00:00
- **Session**: 256bca00-b0cc-4748-b7bc-8b951d19e3ab
- **Category**: query
- **Error**: query_error: Binder Error: Referenced column "table_name" not found in FROM clause!
Candidate bindings: "Date", "Open", "Close"

LINE <NUM>: ... FROM (SELECT * FROM AGMH WHERE Date LIKE <STR>) GROUP BY ...
- **Fix**: Review and rewrite the query with correct syntax, table names, and column names.
- **Retry**: 1
