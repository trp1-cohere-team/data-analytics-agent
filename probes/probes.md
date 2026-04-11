# Adversarial Probe Library
# The Oracle Forge — Data Analytics Agent

**Total probes**: 15  
**Categories covered**: ROUTING (4), JOIN_KEY (4), TEXT_EXTRACT (4), DOMAIN_GAP (3)  
**post_fix_pass threshold**: 0.8

---

## Category: ROUTING — Multi-database routing failures

| Field | ROUTING-001 |
|---|---|
| **id** | ROUTING-001 |
| **category** | ROUTING |
| **query** | "How many orders were placed by customers in California last month?" |
| **description** | Question about orders exists in both SQLite (Yelp) and PostgreSQL. Agent must correctly route to PostgreSQL transactional DB, not SQLite analytical store. |
| **expected_failure_mode** | Agent queries SQLite where orders table doesn't exist; returns empty or errors on missing table. |
| **db_types_involved** | ["postgres", "sqlite"] |
| **fix_applied** | Added domain KB entry clarifying orders table lives in PostgreSQL. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | ROUTING-002 |
|---|---|
| **id** | ROUTING-002 |
| **category** | ROUTING |
| **query** | "What is the average review sentiment score for restaurants in the dataset?" |
| **description** | Sentiment scores are stored as computed fields in DuckDB (analytical), not in MongoDB (raw reviews). Agent must route to DuckDB, not MongoDB. |
| **expected_failure_mode** | Agent queries MongoDB aggregate pipeline for 'sentiment_score' field that doesn't exist; returns null or pipeline error. |
| **db_types_involved** | ["duckdb", "mongodb"] |
| **fix_applied** | Added domain KB entry mapping 'sentiment_score' to DuckDB analytics table. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | ROUTING-003 |
|---|---|
| **id** | ROUTING-003 |
| **category** | ROUTING |
| **query** | "List all business categories and their review counts." |
| **description** | Business categories are in SQLite (Yelp), but review counts require joining with MongoDB reviews. Agent may incorrectly try a single-DB query. |
| **expected_failure_mode** | Agent generates a single PostgreSQL query; fails with 'table not found'. |
| **db_types_involved** | ["sqlite", "mongodb"] |
| **fix_applied** | Added cross-DB query pattern to architecture KB showing SQLite+MongoDB join pattern. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | ROUTING-004 |
|---|---|
| **id** | ROUTING-004 |
| **category** | ROUTING |
| **query** | "Show me the top 10 users by total spending and their last review date." |
| **description** | Spending data is in PostgreSQL; review dates are in MongoDB. Forces cross-DB join that the agent might collapse into one DB. |
| **expected_failure_mode** | Agent generates a PostgreSQL-only query; 'reviews' table not found in PostgreSQL. |
| **db_types_involved** | ["postgres", "mongodb"] |
| **fix_applied** | Multi-DB query plan pattern added to domain KB. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

## Category: JOIN_KEY — Ill-formatted join key mismatches

| Field | JOIN_KEY-001 |
|---|---|
| **id** | JOIN_KEY-001 |
| **category** | JOIN_KEY |
| **query** | "For each customer, show their name from PostgreSQL and their most recent MongoDB order." |
| **description** | PostgreSQL stores customer_id as INTEGER (e.g. 1234). MongoDB stores customer_id as PREFIXED_STRING (e.g. "CUST-01234"). Direct equality join returns zero rows. |
| **expected_failure_mode** | Cross-DB join returns empty result set; no error raised (silent failure). |
| **db_types_involved** | ["postgres", "mongodb"] |
| **fix_applied** | JoinKeyResolver detects INTEGER vs PREFIXED_STRING mismatch; rewrites join with CAST+LPAD transform. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | JOIN_KEY-002 |
|---|---|
| **id** | JOIN_KEY-002 |
| **category** | JOIN_KEY |
| **query** | "Match SQLite product records with DuckDB sales data by product identifier." |
| **description** | SQLite stores product_id as INTEGER. DuckDB stores product_id as PREFIXED_STRING "ITEM-NNNNN" with 5-digit padding. Join produces empty results. |
| **expected_failure_mode** | Query executes without error but returns 0 rows; agent reports "no matching data found". |
| **db_types_involved** | ["sqlite", "duckdb"] |
| **fix_applied** | Added ITEM- prefix pattern to join-key-glossary.md; JoinKeyResolver picks it up. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | JOIN_KEY-003 |
|---|---|
| **id** | JOIN_KEY-003 |
| **category** | JOIN_KEY |
| **query** | "Combine user profile data from PostgreSQL with activity logs from DuckDB." |
| **description** | PostgreSQL user_id is UUID format. DuckDB activity log stores user_id as INTEGER. UUID-to-INTEGER mapping is not defined — should trigger LLM corrector. |
| **expected_failure_mode** | JoinKeyResolver returns None (unsupported UUID→INTEGER pair); agent falls through to LLM corrector. LLM corrector may hallucinate a mapping. |
| **db_types_involved** | ["postgres", "duckdb"] |
| **fix_applied** | Added correction log entry documenting UUID→INTEGER as unsupported; agent now surfaces 'cannot join' explanation. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | JOIN_KEY-004 |
|---|---|
| **id** | JOIN_KEY-004 |
| **category** | JOIN_KEY |
| **query** | "Cross-reference order numbers between the transaction DB and the reporting DB." |
| **description** | Order numbers use different padding widths: PostgreSQL "ORD-007" (3-digit), DuckDB "ORD-00007" (5-digit). JoinKeyResolver must detect width mismatch and repad. |
| **expected_failure_mode** | Equality join returns zero rows; agent does not detect it as a key format issue. |
| **db_types_involved** | ["postgres", "duckdb"] |
| **fix_applied** | JoinKeyResolver PREFIXED_STRING→PREFIXED_STRING repad transform applied; width detected from sample values. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

## Category: TEXT_EXTRACT — Unstructured text extraction failures

| Field | TEXT_EXTRACT-001 |
|---|---|
| **id** | TEXT_EXTRACT-001 |
| **category** | TEXT_EXTRACT |
| **query** | "What is the phone number of the business with the highest average rating?" |
| **description** | Phone numbers are stored in a free-text 'attributes' JSON blob in MongoDB, not as a structured column. Agent must use extract_from_text tool, not a direct field query. |
| **expected_failure_mode** | Agent queries for 'phone' field directly; gets null for most records. Returns wrong or empty answer. |
| **db_types_involved** | ["mongodb"] |
| **fix_applied** | Domain KB updated to note 'phone' lives in attributes JSON blob; LLM sub-call with extraction prompt added to query plan. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | TEXT_EXTRACT-002 |
|---|---|
| **id** | TEXT_EXTRACT-002 |
| **category** | TEXT_EXTRACT |
| **query** | "List all businesses that mention 'gluten-free' in their reviews." |
| **description** | 'gluten-free' appears only in free-text review bodies, not as a structured tag. Requires text search with LLM extraction from review text field. |
| **expected_failure_mode** | Agent generates SQL LIKE '%gluten-free%' on wrong table; or queries a tag column that doesn't exist. |
| **db_types_involved** | ["mongodb", "sqlite"] |
| **fix_applied** | Architecture KB updated: free-text search requires extract_from_text action with review_text field. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | TEXT_EXTRACT-003 |
|---|---|
| **id** | TEXT_EXTRACT-003 |
| **category** | TEXT_EXTRACT |
| **query** | "What parking options do the top-rated restaurants offer?" |
| **description** | Parking information is nested inside a JSON string column 'business_attributes' in SQLite. Requires JSON parsing or LLM extraction, not a direct column read. |
| **expected_failure_mode** | Agent reads 'business_attributes' as a string; returns raw JSON blob as the answer. |
| **db_types_involved** | ["sqlite"] |
| **fix_applied** | Domain KB updated with note that business_attributes is a JSON string; extract_from_text tool must parse it. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | TEXT_EXTRACT-004 |
|---|---|
| **id** | TEXT_EXTRACT-004 |
| **category** | TEXT_EXTRACT |
| **query** | "Summarise the most common complaints from 1-star reviews in the last quarter." |
| **description** | Complaints are only in free-text review bodies. Agent must retrieve relevant reviews and use LLM extraction to summarise themes — a two-step action. |
| **expected_failure_mode** | Agent returns the raw review text instead of a summary; or counts 1-star reviews without reading their content. |
| **db_types_involved** | ["mongodb"] |
| **fix_applied** | Added two-step query pattern to architecture KB: first retrieve reviews, then extract_from_text with summarisation prompt. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

## Category: DOMAIN_GAP — Domain knowledge gaps

| Field | DOMAIN_GAP-001 |
|---|---|
| **id** | DOMAIN_GAP-001 |
| **category** | DOMAIN_GAP |
| **query** | "What does the 'stars' column represent and how is it calculated?" |
| **description** | 'stars' is a Yelp-specific field (1–5 float, consumer-averaged). Without domain KB, the agent cannot explain the calculation methodology. |
| **expected_failure_mode** | Agent gives a generic answer ("it represents a rating out of 5") without the Yelp-specific averaging method. |
| **db_types_involved** | ["sqlite"] |
| **fix_applied** | Added domain KB document explaining Yelp star rating methodology and calculation. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | DOMAIN_GAP-002 |
|---|---|
| **id** | DOMAIN_GAP-002 |
| **category** | DOMAIN_GAP |
| **query** | "Which businesses are 'elite' and what criteria determine elite status?" |
| **description** | 'Elite' is a Yelp user designation (not business), stored in a separate user_elite table. Agent may query businesses table and find nothing. |
| **expected_failure_mode** | Agent queries business table for 'elite' column; returns empty or confused answer. |
| **db_types_involved** | ["sqlite", "postgres"] |
| **fix_applied** | Domain KB updated: 'elite' is a user designation in user_elite junction table, not a business attribute. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |

---

| Field | DOMAIN_GAP-003 |
|---|---|
| **id** | DOMAIN_GAP-003 |
| **category** | DOMAIN_GAP |
| **query** | "What is the difference between 'useful', 'funny', and 'cool' vote counts?" |
| **description** | These are Yelp review vote categories stored as separate integer columns. Without domain context, the agent treats them as synonyms or ignores distinctions. |
| **expected_failure_mode** | Agent sums all three as a single 'engagement' metric instead of distinguishing them per the Yelp schema. |
| **db_types_involved** | ["mongodb"] |
| **fix_applied** | Domain KB document added explaining Yelp vote taxonomy: useful/funny/cool are independent peer feedback dimensions. |
| **error_signal** | null |
| **correction_attempt_count** | null |
| **observed_agent_response** | null |
| **pre_fix_score** | null |
| **post_fix_score** | null |
| **post_fix_pass** | null |
