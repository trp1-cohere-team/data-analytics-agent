# Common Query Patterns for DAB Datasets

## Dataset Overview

| Dataset | DB Type | Key Tables |
|---------|---------|-----------|
| bookreview | postgres + sqlite | books_info, review |
| stockmarket | postgres | stock_prices, companies |
| stockindex | postgres | index_components, prices |
| music_brainz_20k | postgres | artist, release, recording |
| yelp | postgres | business, review, user |

## PostgreSQL — Aggregation Patterns

```sql
-- Average by decade
SELECT FLOOR(year / 10) * 10 AS decade, AVG(rating) as avg_rating
FROM books_info
GROUP BY decade
HAVING COUNT(DISTINCT book_id) >= 10
ORDER BY avg_rating DESC
LIMIT 1;

-- Correlation pattern
SELECT CORR(price, rating_number) FROM books_info;
```

## SQLite — Review Aggregation

```sql
-- Top rated items with minimum review threshold
SELECT item_id, AVG(rating) as avg_rating, COUNT(*) as review_count
FROM review
GROUP BY item_id
HAVING review_count >= 5
ORDER BY avg_rating DESC
LIMIT 10;
```

## Cross-Database Join Pattern

When a question involves two databases (e.g., bookreview: books_database=postgres, review_database=sqlite):
1. Query each database separately
2. Join on common key (e.g., book_id, asin)
3. Combine results in synthesized answer

## MongoDB Aggregation Pattern

```json
[
  {"$match": {"category": "Electronics"}},
  {"$group": {"_id": "$brand", "avg_price": {"$avg": "$price"}}},
  {"$sort": {"avg_price": -1}},
  {"$limit": 5}
]
```

## DuckDB LATERAL JOIN Pattern (common DAB trap)

```sql
-- LATERAL is supported in DuckDB (unlike standard SQLite)
SELECT t.category, unnested.value
FROM table1 t, LATERAL UNNEST(t.array_col) AS unnested(value)
WHERE unnested.value > 100;
```

Note: DuckDB supports LATERAL, UNNEST, and window functions. Use query_duckdb for these patterns.
