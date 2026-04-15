# DataAgentBench (DAB) Format and Scoring

## Benchmark Overview

DAB evaluates multi-database analytics agents on 12 real-world datasets.
Each dataset has 3-10 queries. Each query requires querying 1-2 databases.

## Query Structure

```
external/DataAgentBench/
  query_{dataset}/
    db_config.yaml          # database connection types and paths
    db_description.txt      # schema + field descriptions
    query{N}/
      query.json            # question (string)
      ground_truth.csv      # expected answer (CSV, first data row)
      validate.py           # validation script (not used in offline mode)
```

## db_config.yaml Format

```yaml
db_clients:
  books_database:
    db_type: postgres
    db_name: bookreview_db
    sql_file: query_dataset/books_info.sql
  review_database:
    db_type: sqlite
    db_path: query_dataset/review_query.db
```

## pass@1 Scoring

pass@1 = fraction of queries where at least 1 trial produced a passing answer.

A trial passes if the agent's answer contains the ground truth string (case-insensitive substring match).

## Failure Categories (FR-04)

| Category | Description | Example |
|----------|-------------|---------|
| query | SQL syntax or logic error | Missing GROUP BY clause |
| join-key | Wrong or missing join column | `book_id` vs `asin` |
| db-type | Wrong database tool selected | Used postgres tool on sqlite dataset |
| data-quality | Ground truth data not in DB | Temporal mismatch, missing records |

## Evaluation Datasets

| Dataset | DB Types | Queries |
|---------|---------|---------|
| bookreview | postgres + sqlite | 5 |
| stockmarket | postgres | 5 |
| stockindex | postgres | 3 |
| music_brainz_20k | postgres | 5 |
| yelp | postgres | 5 |
| googlelocal | postgres | 3 |
| crmarenapro | postgres | 5 |
| DEPS_DEV_V1 | postgres | 3 |
| GITHUB_REPOS | postgres | 3 |
| PANCANCER_ATLAS | postgres | 3 |
| PATENTS | postgres | 3 |
| agnews | postgres | 3 |
