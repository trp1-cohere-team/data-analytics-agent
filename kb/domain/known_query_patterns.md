# Known Query Patterns (Validated)

## Purpose
Provide reusable query templates that avoid common agent failures.

---

## 1. Safe Aggregation Pattern

Problem:
Agents forget GROUP BY → SQL errors

Pattern:
SELECT col, AGG(metric)
FROM table
GROUP BY col

Rule:
Every non-aggregated column must be in GROUP BY

---

## 2. Join with Explicit Keys

Problem:
Hallucinated joins

Pattern:
SELECT *
FROM A
JOIN B ON A.key = B.key

Rules:
- NEVER infer join keys
- MUST exist in schema_registry
- If missing → trigger perception error

---

## 3. Null-Safe Filtering

Problem:
Incorrect filtering due to NULL

Pattern:
WHERE col IS NOT NULL
AND col = value

---

## 4. Time Range Queries

Problem:
Incorrect date filtering

Pattern:
WHERE date_col BETWEEN start AND end

Rules:
- Normalize timezone
- Avoid string comparison

---

## 5. Defensive LIMIT

Problem:
Unbounded queries

Pattern:
SELECT ...
FROM ...
LIMIT 100

---

## 6. Schema Validation First

Problem:
Querying non-existent columns

Pattern:
STEP 1: Inspect schema  
STEP 2: Generate query

---

## 7. Multi-Step Decomposition

Problem:
Complex queries fail

Pattern:
- Step 1: subquery
- Step 2: aggregate
- Step 3: join

---

## 8. Retry Strategy (DAB-aligned)

If query fails:
1. Classify error_type
2. Apply fix:

- knowledge → retrieve schema
- reasoning → simplify query
- perception → re-check fields
- execution → retry tool

---

## 9. Anti-Patterns (DO NOT DO)

- SELECT * without LIMIT
- JOIN without ON clause
- GROUP BY mismatch
- implicit casting assumptions

---

## 10. Injection Test

Prompt:
"Generate a SQL query joining users and orders"

Expected:
- explicit join key
- schema-aware fields
- LIMIT applied
