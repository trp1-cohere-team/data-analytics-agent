# Correction Patterns

Common correction categories used by OracleForge runtime:

1. `query`
- SQL syntax, missing columns, wrong table names.
- Typical fix: rewrite query with schema-grounded identifiers.

2. `join-key`
- Wrong key assumptions across systems.
- Typical fix: normalize identifier formats before reconciliation.

3. `db-type`
- Wrong backend/tool selection or backend availability issues.
- Typical fix: switch to correct tool or repair route hints.

4. `data-quality`
- Null-heavy or malformed values that break assumptions.
- Typical fix: add defensive filters and fallback summarization.
