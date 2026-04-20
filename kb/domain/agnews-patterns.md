# AG News Query Patterns

Each pattern states the user intent, data sources, and computation path.
**Always COMPUTE the final value — do not dump raw rows.**

## Data sources

- `articles_database` (MongoDB) — `articles` collection.
  Fields: `article_id` (int), `title` (str), `description` (str).
- `metadata_database` (SQLite):
  - `authors` — `author_id` (int), `name` (str).
  - `article_metadata` — `article_id` (int), `author_id` (int), `region` (str),
    `publication_date` (str, format `YYYY-MM-DD`).

## Categories (IMPORTANT)

Articles are NOT labeled with a category column. All articles belong to exactly one of:
`World`, `Sports`, `Business`, `Science/Technology`.
Classifying requires reading `title` + `description` and applying LLM judgment.

When a query asks about a category (e.g. "sports articles", "business articles"):
- Fetch title + description from MongoDB for candidate articles.
- Have the LLM classify each into one of the four categories based on the text content.
- Then compute the statistic (ratio, count, fraction, etc.) on the classified set.

## Joining across DBs

- Mongo articles.article_id ↔ SQLite article_metadata.article_id (integer key).
- SQLite article_metadata.author_id ↔ SQLite authors.author_id.

## Pattern 1: Longest-description article within a category

- Intent: "sports article whose description has the greatest number of characters"
- Steps:
  1. Fetch all articles (title + description) from MongoDB.
  2. LLM-classify each as World/Sports/Business/Science/Technology based on the text.
  3. Filter to the target category; compute `LENGTH(description)`.
  4. Return the `title` with the max length — return the single title string (not a row dump).

## Pattern 2: Fraction of an author's articles in a category

- Intent: "fraction of Amy Jones's articles in Science/Technology"
- Steps:
  1. Join SQLite `authors` + `article_metadata` to get all article_ids for the author.
  2. Fetch title + description from MongoDB for those article_ids.
  3. LLM-classify each; count category matches / total articles by that author.
- Output: a single decimal fraction (e.g. `0.14414414414414414`), not a list.

## Pattern 3: Average articles per year in a region and category

- Intent: "average business articles per year in Europe from 2010 to 2020 inclusive"
- Steps:
  1. SQLite filter: `region` LIKE Europe indicator, `publication_date` BETWEEN '2010-01-01' AND '2020-12-31'.
  2. Fetch matching articles from Mongo, LLM-classify for category.
  3. Compute `COUNT(matches) / 11` years (2010..2020 inclusive = 11 years).
- Output: a single decimal number.

## Common mistakes

- Returning article_id lists or Mongo dicts verbatim as the answer.
- Forgetting to classify before filtering by category (there is no `category` column).
- Using the wrong year span for "2010 to 2020 inclusive" (it is 11 years, not 10).
- Returning MongoDB `ObjectId` / `_id` values when only `title` or a count is asked.
