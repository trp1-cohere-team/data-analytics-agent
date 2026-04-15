# Join-Key Glossary for DAB Datasets

## Common Join Keys by Dataset

### bookreview
- `books_info.book_id` ↔ `review.asin` (note: field name differs across tables)
- `books_info.asin` may also appear in older schema versions

### stockmarket
- `companies.ticker` ↔ `stock_prices.ticker`
- `companies.company_id` ↔ `financials.company_id`

### music_brainz_20k
- `artist.gid` ↔ `artist_credit_name.artist`
- `release.id` ↔ `release_group_secondary_type_join.release_group`
- `recording.id` ↔ `track.recording`

### yelp
- `business.business_id` ↔ `review.business_id`
- `user.user_id` ↔ `review.user_id`

## Failure Category: join-key

When a join fails, classify as `join-key` and check:
1. The actual column names in both tables (they may differ: `id` vs `book_id`)
2. Whether a cross-db query requires Python-level join (fetch both, join in memory)
3. Data type mismatches (integer ID vs string ID)

## Cross-DB Join Strategy

DAB queries often span two databases (e.g., postgres + sqlite).
The agent should:
1. Query database A for intermediate results
2. Query database B with those results as a filter
3. Combine in the synthesis step

Never attempt to JOIN across two different database connections in a single SQL statement.
