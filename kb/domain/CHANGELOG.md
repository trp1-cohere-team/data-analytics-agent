# KB / domain — CHANGELOG

Documents in this directory describe business domain knowledge: which database
contains which data, routing rules, field meanings, and data conventions.

---

## v1.0.0 — Initial injection (Week 8, Day 1)

**Documents added:**
- `routing_rules.md` — which DB to query for which business question type
- `field_glossary.md` — canonical field names across all 4 databases
- `data_conventions.md` — date formats, currency units, ID formats per DB

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "How many orders were placed by customers in California last month?" | Routes to PostgreSQL, not SQLite | ✅ |
| "What is the average review sentiment score for restaurants?" | Routes to DuckDB analytical store | ✅ |
| "Find all restaurants with more than 100 reviews" | Routes to MongoDB (raw reviews) | ✅ |
| "List businesses in Las Vegas" | Routes to SQLite (Yelp dataset) | ✅ |

**Injected by:** [TEAM MEMBER 3]
**Mob approval:** [DATE] — approved by team

---

## v1.1.0 — Added cross-DB routing clarifications (Week 8, Day 3)

**Documents added:**
- `cross_db_queries.md` — questions requiring data from multiple DBs

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "Which customers ordered from 5-star restaurants?" | Joins PostgreSQL (orders) + MongoDB (reviews) | ✅ |
| "Compare transaction counts to review counts by city" | PostgreSQL + SQLite merge | ✅ |

**Injected by:** [TEAM MEMBER 3]

---

## v1.2.0 — Probe-driven fixes (Week 8, Day 4)

**Documents updated:**
- `routing_rules.md` — clarified orders table lives only in PostgreSQL
- `field_glossary.md` — added `sentiment_score` → DuckDB analytics table mapping

**Fix for probes:** ROUTING-001, ROUTING-002
