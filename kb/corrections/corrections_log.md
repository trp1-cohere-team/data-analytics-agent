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
