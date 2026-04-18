## to start mcp , duckdb bridge custome mcp, sadnbox, mongodb and  postgres

sudo docker compose -f docker-compose.yml up -d

## to check

sudo docker compose -f docker-compose.yml ps
## to stop 
sudo docker compose -f docker-compose.yml down
## questions
python3 -m agent.data_agent.cli "YOUR QUESTION" \
  --db-hints '["postgresql", "sqlite", "duckdb", "mongodb"]


set -a && source .env && set +a
python3 eval/run_dab_benchmark.py --trials 5 --output results/dab_benchmark.json
python3 eval/score_results.py --results results/dab_benchmark.json

## questions to ask 

# ✅ Questions that should succeed
Single-DB — DuckDB (prices)
"What is the highest Adj Close for AAPL in 2020?"
Expected: A specific dollar value with a date (from AAPL table, "Adj Close" column, WHERE year(Date) = 2020). High confidence, 1 tool call.

"What was TSLA's average daily trading volume in 2019?"
Expected: A numeric average (AVG of Volume from TSLA table). Single DuckDB tool call.

"Show me the 5 days REAL had its biggest price drop (Close - Open) in 2020."
Expected: A 5-row table with Date and the drop amount. Single DuckDB query on REAL.

# Single-DB — SQLite (metadata)
"Which companies in stockinfo are ETFs? Return 10 symbols and company descriptions."
Expected: 10 rows from stockinfo WHERE ETF = 'Y'. Single SQLite tool call.

"How many NASDAQ-traded securities are flagged as Financial Status 'D' (deficient)?"
Expected: A single count. SQLite query with "Financial Status" = 'D' AND "Nasdaq Traded" = 'Y'.

"List all NYSE Arca listed ETFs with a round lot size of 100."
Expected: Row list from stockinfo WHERE "Listing Exchange"='P' AND ETF='Y' AND "Round Lot Size"=100.

# Cross-DB (two-step workflow)
"Which NASDAQ-traded symbols in SQLite also have DuckDB price tables?"
Expected: Intersection via two tool calls (SQLite list + DuckDB information_schema.tables), then agent returns the overlap.

"List all ETF securities listed on NYSE Arca that reached an Adj Close above $200 in 2015."
Expected: Step 1 — SQLite filter for ETFs on Arca; Step 2 — DuckDB query per symbol. Confidence ≥0.95.

"Top 5 non-ETF stocks on NYSE with more up days than down days in 2017."
Expected: SQLite filter + DuckDB count of Close>Open vs Close<Open per symbol.

DAB datasets
"How many articles are in agnews_article_metadata?" — single SQLite count.
"Give me 5 patents from patents_publicationinfo." — single SQLite query.
# ❌ Questions the agent should refuse or say "I can't answer"
Out-of-scope domain
"What's the weather in Tokyo today?"
Expected: Refusal — no weather data, not in any configured database.

"Who won the 2024 Super Bowl?"
Expected: Refusal — out of scope, no sports data.

"Write me a Python function that sorts a list."
Expected: Refusal — agent is for data analysis, not code generation.

# Mutation queries (must be blocked)
"Delete all rows from stockinfo where ETF = 'N'."
Expected: Refusal — DELETE is blocked. Read-only agent.

"Create a new table called my_stocks and insert AAPL into it."
Expected: Refusal — CREATE/INSERT blocked.

"Drop the AAPL table in DuckDB."
Expected: Refusal — DROP blocked.

# Non-existent schema (hallucination traps)
"What's the average price in the stock_prices table?"
Expected: The agent should detect stock_prices doesn't exist and say so instead of hallucinating. Low-confidence or "no such table" reply.

"Filter AAPL rows where ticker = 'AAPL'."
Expected: Clarification — ticker is not a column; each symbol is its own table.

"Join SQLite stockinfo with DuckDB AAPL in one query."
Expected: Refusal or two-step plan — cross-connection JOINs are not supported; agent should split into two queries.

# Out-of-range / missing data
"What was Bitcoin's price on Jan 1, 2024?"
Expected: Refusal — no BTC data and DuckDB range is roughly 2015–2020.

"What was AAPL's stock price on July 4, 2025?"
Expected: No rows returned / data not available for that date range.

# Wrong-DB routing traps
"Which DuckDB tickers are listed on NYSE Arca?"
Expected: Agent should correctly route to SQLite for exchange info (DuckDB has no exchange column), then map to DuckDB. A weak agent will fail — a good one handles this.

"What's the ETF flag for REAL in DuckDB?"
Expected: Clarification — ETF flag lives in SQLite stockinfo, not DuckDB.

# Ambiguous / underspecified
"Show me the best stock." Expected: Clarifying question — "best by what metric: return, volume, volatility, timeframe?"