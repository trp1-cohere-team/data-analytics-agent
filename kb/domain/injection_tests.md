# Injection Tests — Domain KB

## Test 1 — Join Key

Question:
"How should customer IDs be joined across PostgreSQL and MongoDB?"

Expected:
- identify format mismatch
- apply normalization rule

Pass:
Model explicitly mentions prefix removal or format alignment.

---

## Test 2 — Domain Definition

Question:
"What is an active customer?"

Expected:
- purchase within last 90 days

Fail Case:
"customer exists in table"

---

## Test 3 — Repeat Purchase Rate

Question:
"How do you compute repeat purchase rate?"

Expected:
- customer-level aggregation
- more than one purchase condition

---

## Test 4 — Unstructured Data

Question:
"How do you count negative support tickets?"

Expected:
- extract sentiment from text first
- then count

Fail Case:
count raw text entries

---

## Test 5 — Correlation

Question:
"Does correlation mean statistical correlation?"

Expected:
- no, unless explicitly computed
- default to descriptive comparison
