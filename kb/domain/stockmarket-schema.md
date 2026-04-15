# Stockmarket Dataset Schema

## Overview
Two databases work together for stock market queries.

## 1. stockinfo_database (SQLite — query_sqlite tool)
Contains metadata about publicly traded stocks and ETFs on U.S. exchanges.

**Table: stockinfo**
| Column | Type | Description |
|--------|------|-------------|
| Nasdaq Traded | TEXT | Whether stock is traded on NASDAQ |
| Symbol | TEXT | Stock ticker symbol (e.g. AAPL, REAL) |
| Listing Exchange | TEXT | Exchange code: N=NYSE, Q=NASDAQ, A=NYSE MKT, P=NYSE ARCA |
| Market Category | TEXT | Q=NASDAQ Global Select, G=NASDAQ Global, S=NASDAQ Capital |
| ETF | TEXT | Y if ETF, N if stock |
| Round Lot Size | REAL | Standard trading unit size |
| Test Issue | TEXT | Y if test issue |
| Financial Status | TEXT | N=Normal, D=Deficient, E=Delinquent, Q=Bankrupt |
| NextShares | TEXT | NextShares designation |
| Company Description | TEXT | Full company name and description |

**Example query — find ticker by company name:**
```sql
SELECT Symbol, "Company Description"
FROM stockinfo
WHERE "Company Description" LIKE '%RealReal%'
```

## 2. stocktrade_database (DuckDB — query_duckdb tool)
Contains daily price data. Each table is named after the stock's ticker symbol.

**Table schema (one table per ticker, e.g. REAL, AAPL, TSLA):**
| Column | Type | Description |
|--------|------|-------------|
| Date | TEXT | Trading date (YYYY-MM-DD format) |
| Open | DOUBLE | Opening price |
| High | DOUBLE | Highest price during the day |
| Low | DOUBLE | Lowest price during the day |
| Close | DOUBLE | Closing price |
| Adj Close | DOUBLE | Adjusted closing price (accounts for splits/dividends) |
| Volume | BIGINT | Number of shares traded |

**Example query — max adjusted close price in 2020 for ticker REAL:**
```sql
SELECT MAX("Adj Close") FROM REAL WHERE Date LIKE '2020%'
```

**Example query — average volume for AAPL in Q1 2020:**
```sql
SELECT AVG(Volume) FROM AAPL WHERE Date BETWEEN '2020-01-01' AND '2020-03-31'
```

## Multi-step workflow for stock questions:
1. **Step 1** — Use `query_sqlite` to find the ticker symbol from the company name
2. **Step 2** — Use `query_duckdb` with the ticker as the table name for price/volume data

## Important notes:
- Column names with spaces must be quoted: `"Adj Close"`, `"Company Description"`
- Date filter uses LIKE for year: `WHERE Date LIKE '2020%'`
- The DuckDB table name IS the ticker symbol (e.g. FROM REAL, FROM AAPL)
- The RealReal, Inc. ticker symbol is **REAL**
