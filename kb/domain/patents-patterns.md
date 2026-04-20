# Patents Query Patterns

Each pattern states the user intent, data sources, and computation path.
**Always COMPUTE in SQL — do not return raw rows.**

## Data sources

- `publication_database` (SQLite) — `publicationinfo` table. Many fields are natural-language or
  JSON-like strings, not structured values:
  - `Patents_info` (text): NL summary including `application_number`, `publication_number`,
    `assignee_harmonized`, `country_code`. Use `LIKE '%assignee_harmonized: UNIV CALIFORNIA%'`
    style matching.
  - `cpc` (text): JSON-like list of CPC entries. Each entry has `code` and metadata.
    Use SQLite `json_each` / regex to extract codes.
  - `citation` (text): list of cited patent numbers and non-patent literature.
  - `publication_date`, `filing_date`, `grant_date`: **natural-language dates** (e.g. "March 15th, 2020"),
    not ISO. Parse with `strftime`/`date` only after converting; often easier to do substring-match
    on the year (`LIKE '%2019%'`).
- `CPCDefinition_database` (Postgres) — `cpc_definition` table: CPC hierarchy.
  Key fields: `symbol` (CPC code), `titleFull` (descriptive title), `level` (int: 1-5),
  `parents` (JSON-like parent list).

## Joining across DBs

- publicationinfo.cpc ↔ cpc_definition.symbol (extract code from the JSON-like cpc field, then
  look up titleFull/level in Postgres).

## Pattern 1: Exponential moving average (EMA) of yearly filings by CPC

- Formula: `EMA_t = alpha * value_t + (1 - alpha) * EMA_{t-1}` with smoothing `alpha` (e.g. 0.2).
- Implement with a window function using recursive CTE, or compute year-by-year in SQL:
  ```sql
  WITH yearly AS (
    SELECT cpc_code, year, COUNT(*) AS filings
    FROM ... GROUP BY cpc_code, year
  ),
  ema AS (
    SELECT cpc_code, year, filings,
           -- recursive EMA calculation
  )
  SELECT cpc_code FROM ema ORDER BY ema_value DESC LIMIT 1
  ```
- Filter to `level = 5` CPC codes when the question asks for "level 5" or "CPC group".

## Pattern 2: Country / date-range filtering

- To filter Germany: `LIKE '%country_code: DE%'` in `Patents_info`.
- For "second half of 2019": match both months (`'July 2019'`..`'December 2019'`) in the
  natural-language date strings OR regex-extract the year and month.
- Return shape `titleFull, cpc_group, best_year` — always include the cpc_definition.titleFull.

## Pattern 3: Citation networks (cited-by / citing)

- `citation` in publicationinfo lists patent numbers cited BY this patent.
- To find "assignees who cited UNIV CALIFORNIA": find publications whose `citation` field
  contains UNIV CALIFORNIA's publication numbers; then extract their `assignee_harmonized` from
  `Patents_info`.
- Return shape `citing_assignee, titleFull`; exclude UNIV CALIFORNIA from its own citation set.

## Common mistakes

- Dumping the raw `citation` JSON-like string as the answer.
- Treating `publication_date` / `filing_date` as ISO dates — they are natural language.
- Forgetting to exclude the source assignee from its own citations.
- Ignoring the `level` filter when the question asks for a specific CPC hierarchy level.
