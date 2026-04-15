# Stockmarket Dataset Schema

Ground truth: DataAgentBench `query_stockmarket`.

## Dataset Shape

- Two databases are used together.
- `stockinfo_database` is `SQLite`.
- `stocktrade_database` is `DuckDB`.
- The workflow is always:
  1. find the security universe in `stockinfo`
  2. map each `Symbol` to a DuckDB table name
  3. query those ticker tables for price and volume facts

## 1. stockinfo_database

- Database type: `SQLite`
- Table: `stockinfo`
- Grain: one row per listed security
- Canonical key: `Symbol`

| Column | Type | Meaning |
| --- | --- | --- |
| `Nasdaq Traded` | `TEXT` | `Y`/`N` flag for NASDAQ-traded securities |
| `Symbol` | `TEXT` | Ticker symbol; this is also the DuckDB table name |
| `Listing Exchange` | `TEXT` | Exchange code: `N` NYSE, `Q` NASDAQ, `A` NYSE MKT, `P` NYSE Arca |
| `Market Category` | `TEXT` | NASDAQ market tier: `Q`, `G`, `S` |
| `ETF` | `TEXT` | `Y` for ETF, `N` for non-ETF stock |
| `Round Lot Size` | `REAL` | Standard trading lot size |
| `Test Issue` | `TEXT` | Test security flag |
| `Financial Status` | `TEXT` | Distress/status code such as `N`, `D`, `E`, `Q`, or null |
| `NextShares` | `TEXT` | NextShares designation |
| `Company Description` | `TEXT` | Company/security description text |

## 2. stocktrade_database

- Database type: `DuckDB`
- Storage pattern: one table per ticker symbol
- Grain: one row per ticker per trading day
- Canonical key: `(table name = Symbol, Date)`

| Column | Type | Meaning |
| --- | --- | --- |
| `Date` | `TEXT` | Trading date in `YYYY-MM-DD` format |
| `Open` | `DOUBLE` | Opening price |
| `High` | `DOUBLE` | Daily high |
| `Low` | `DOUBLE` | Daily low |
| `Close` | `DOUBLE` | Closing price |
| `Adj Close` | `DOUBLE` | Adjusted close; quote because of the space |
| `Volume` | `BIGINT` | Daily traded volume |

## Key Relationship

- Safe cross-database mapping:
  - `stockinfo.Symbol` -> DuckDB table name in `stocktrade_database`
- Important constraint:
  - there is no `ticker` or `symbol` column inside the DuckDB price tables
  - the ticker is encoded in the table name itself

## Query Workflow

### Company name to ticker

Use SQLite first:

```sql
SELECT Symbol, "Company Description"
FROM stockinfo
WHERE "Company Description" LIKE '%RealReal%'
```

### Ticker to price history

Then query DuckDB using the ticker as the table:

```sql
SELECT MAX("Adj Close") AS max_adj_close
FROM REAL
WHERE Date >= '2020-01-01' AND Date < '2021-01-01'
```

## Common Filters

- Exchange filter lives in SQLite:
  - `Listing Exchange = 'N'` for NYSE
  - `Listing Exchange = 'P'` for NYSE Arca
- Market tier filter lives in SQLite:
  - `Market Category = 'S'` for NASDAQ Capital Market
- ETF flag lives in SQLite:
  - `ETF = 'Y'` or `ETF = 'N'`
- Price and volume facts live only in DuckDB ticker tables:
  - `Open`, `High`, `Low`, `Close`, `"Adj Close"`, `Volume`

## Safe Patterns

- Filter the security universe in `stockinfo` first.
- Confirm the ticker table exists in DuckDB before querying it.
- Build `UNION ALL` queries across ticker tables when ranking many securities.
- Quote `"Adj Close"` and `"Company Description"` because their names contain spaces.

## Unsafe Assumptions

- Do not query a non-existent shared table like `stock_prices`.
- Do not assume a DuckDB price table has a `Symbol` column.
- Do not apply exchange, ETF, or market-category filters in DuckDB; those attributes live in SQLite.
- Do not treat `Company Description` as a join key; use it only to discover the `Symbol`.

## Analyst Shortcuts

- `REAL` is the ticker for The RealReal.
- If the question asks about "companies", the answer still needs to route through `stockinfo.Symbol`.
- If the question asks about "daily moves", "adjusted close", or "volume", the actual computation belongs in DuckDB after the ticker universe is known.
