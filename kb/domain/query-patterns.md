# Stockmarket Query Patterns

Each pattern states the user intent, data sources, and computation path.

## Pattern 1: Company name to ticker lookup

- Intent: "What is the ticker for Company X?"
- Source: `stockinfo`
- Logic: search `Company Description`, return `Symbol`
- Notes: description text is for lookup only

## Pattern 2: Single-ticker price statistic

- Intent: "What was the max adjusted close for REAL in 2020?"
- Source: DuckDB ticker table
- Logic: query the symbol-named table and aggregate `"Adj Close"` over a date range
- Notes: quote `"Adj Close"`

## Pattern 3: Filter in SQLite, compute in DuckDB

- Intent: "Which NYSE Arca ETFs crossed an adjusted close above 200 in 2015?"
- Source: `stockinfo` + DuckDB ticker tables
- Logic:
  - use SQLite to get symbols where `ETF = 'Y'` and `Listing Exchange = 'P'`
  - query each ticker table in DuckDB
  - keep securities whose yearly `MAX("Adj Close") > 200`

## Pattern 4: Distressed-company volume analysis

- Intent: "What was the average 2008 volume for financially troubled NASDAQ securities?"
- Source: `stockinfo` + DuckDB ticker tables
- Logic:
  - use SQLite to find `Nasdaq Traded = 'Y'` and `Financial Status IN ('D', 'E')`
  - calculate `AVG(Volume)` in each symbol table for 2008

## Pattern 5: Up-days versus down-days ranking

- Intent: "Which non-ETF NYSE stocks had more up days than down days in 2017?"
- Source: `stockinfo` + DuckDB ticker tables
- Logic:
  - filter `Listing Exchange = 'N'` and `ETF = 'N'` in SQLite
  - in DuckDB count `Close > Open` and `Close < Open`
  - rank by `(up_days - down_days)`

## Pattern 6: Volatile-day ranking

- Intent: "Which NASDAQ Capital Market stocks had the most >20% intraday range days in 2019?"
- Source: `stockinfo` + DuckDB ticker tables
- Logic:
  - filter `Market Category = 'S'`, `Nasdaq Traded = 'Y'`, `ETF = 'N'`
  - count days where `(High - Low) > 0.2 * Low`
  - rank descending

## Pattern 7: Exchange or ETF cohort comparison

- Intent: "Compare ETFs and non-ETFs by average volume or peak price."
- Source: `stockinfo` + DuckDB ticker tables
- Logic:
  - split the cohort in SQLite using `ETF`
  - compute per-ticker metrics in DuckDB
  - compare cohort-level summaries in synthesis

## Pattern 8: Table-existence-aware batch scan

- Intent: "Analyze all securities matching a metadata filter."
- Source: `stockinfo` + `information_schema.tables` + DuckDB ticker tables
- Logic:
  - get symbols from SQLite
  - intersect with available DuckDB tables
  - only query symbols that exist as tables

## Pattern 9: Date-window performance query

- Intent: "What was the return for ticker X between two dates?"
- Source: DuckDB ticker table
- Logic:
  - get start and end close prices inside the table
  - compute return in SQL or synthesis
- Notes: no SQLite query is needed if the ticker is already known

## Pattern 10: Metadata-first natural language routing

- Intent: "Top 5 non-ETF NYSE securities by some market metric"
- Source: SQLite first, DuckDB second
- Logic:
  - all instrument classification filters go to `stockinfo`
  - all market fact computations go to symbol-named DuckDB tables

## Pattern Guards

- Never assume a single shared price table exists.
- Never filter on exchange or ETF fields in DuckDB.
- Never use `Company Description` as a durable join key.
- Always treat `Symbol` as the bridge from metadata to per-ticker tables.
