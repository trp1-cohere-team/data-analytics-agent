# Shared Utilities

Reusable helper modules used across runtime and evaluation flows.

## `utils/db_utils.py`
Purpose:
- DB-kind normalization and SQL-safe log sanitization helpers.
- Used by runtime dispatch and trace emission.

Usage example:
```python
from utils.db_utils import db_type_from_kind, sanitize_sql_for_log

assert db_type_from_kind("postgres-sql") == "postgres"
print(sanitize_sql_for_log("SELECT * FROM users WHERE id = 42 AND name = 'Ada'"))
```

## `utils/text_utils.py`
Purpose:
- Keyword extraction and overlap scoring helpers for KB retrieval.
- Used by `knowledge_base.py` ranking logic.

Usage example:
```python
from utils.text_utils import extract_keywords, score_overlap

keywords = extract_keywords("How do we route duckdb tools safely?")
score = score_overlap(keywords, "duckdb tools are routed through a bridge")
print(keywords, score)
```

## `utils/trace_utils.py`
Purpose:
- `TraceEvent` factory and human-readable trace formatting.
- Used by `events.py` and runtime conductor.

Usage example:
```python
from utils.trace_utils import build_trace_event, format_trace_summary

ev = build_trace_event(event_type="session_start", session_id="demo")
print(format_trace_summary([ev]))
```
