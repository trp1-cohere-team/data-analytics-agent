# Join-Key Glossary

This glossary is stockmarket-focused. It defines the only safe structural mapping between the SQLite metadata layer and the DuckDB price layer.

## Canonical Mapping

| Concept | SQLite source | DuckDB source | Rule |
| --- | --- | --- | --- |
| Security / ticker | `stockinfo.Symbol` | table name | The ticker symbol is the bridge from metadata to price history. |
| Daily market record | `stockinfo.Symbol` + date range intent | `(table name = Symbol, Date)` | Resolve ticker first, then query that ticker table by date. |

## What Counts as a Join Here

- This dataset does not use a normal row-to-row foreign key join across two tables.
- The "join" is a two-step mapping:
  1. query `stockinfo` to get a list of symbols
  2. query those symbol-named DuckDB tables and combine results in the agent layer

## Safe Lookup Keys

| Natural language concept | Safe field | Why |
| --- | --- | --- |
| company name | `Company Description` -> `Symbol` | Description text is used to discover the ticker, not to join directly to DuckDB facts |
| exchange | `Listing Exchange` | Exchange code is only stored in SQLite |
| ETF vs stock | `ETF` | Instrument type is only stored in SQLite |
| NASDAQ market tier | `Market Category` | Market tier is only stored in SQLite |
| distressed/troubled company | `Financial Status` | Distress flags are only stored in SQLite |
| price or volume | DuckDB ticker table columns | OHLCV facts only live in DuckDB |

## No-Safe-Join Warnings

- There is no shared `ticker` column inside DuckDB price tables.
- There is no safe join on `Company Description`.
- There is no safe way to filter on exchange or ETF status inside DuckDB without first using SQLite.
- There is no single cross-db SQL statement that should join SQLite metadata directly to DuckDB tables in one query tool call.

## Working Rules

### Rule 1: Resolve the security universe first

- Use `stockinfo` to answer:
  - which symbols are on NYSE
  - which symbols are ETFs
  - which symbols are troubled NASDAQ securities
  - which symbols belong to NASDAQ Capital Market

### Rule 2: Treat the symbol as a table selector

- Example:
  - `Symbol = 'REAL'`
  - query DuckDB table `REAL`

### Rule 3: Check table existence

Use DuckDB metadata before large cross-symbol scans:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'main'
```

### Rule 4: Combine results with generated `UNION ALL`

For ranking many securities:
- query SQLite for symbols
- generate one `SELECT ... FROM "TICKER"` per symbol
- combine with `UNION ALL`

## Common Failure Cases

| Bad assumption | Correct rule |
| --- | --- |
| `stock_prices.ticker` exists | There is no shared `stock_prices` table in this dataset |
| join on `Company Description` | Use `Company Description` only to discover `Symbol` |
| use DuckDB to filter `ETF = 'Y'` | ETF flag lives in SQLite `stockinfo` |
| query `Adj Close` without quotes | Use `"Adj Close"` |
| assume every SQLite symbol has a DuckDB table | Verify existence through `information_schema.tables` |
