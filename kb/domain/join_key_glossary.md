# Join Key Glossary

## Purpose

Documents how entity identifiers differ across data sources.

---

## Customer ID

PostgreSQL:
- integer (e.g. 123)

MongoDB:
- string with prefix (e.g. "CUST-00123")

Resolution Rule:
- strip prefix "CUST-"
- convert to integer
- align formats before join

---

## Product Code

PostgreSQL:
- uppercase string (e.g. "PRD_A12")

MongoDB:
- lowercase or mixed case (e.g. "prd_a12")

Resolution Rule:
- normalize to uppercase before comparison

---

## Order ID

PostgreSQL:
- integer

DuckDB:
- zero-padded string (e.g. "000123")

Resolution Rule:
- remove padding or cast to integer

---

## Key Principle

Never join directly across systems without:
1. inspecting sample values
2. identifying format differences
3. applying normalization

Failure to do so leads to silent incorrect results.
