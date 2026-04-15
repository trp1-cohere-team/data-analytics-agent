"""Database utility helpers.

FR-03: Kind-to-DB-type mapping.
SEC-03: SQL sanitization for safe logging.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Kind → db_type mapping (matches tools.yaml kinds)
# ---------------------------------------------------------------------------

_KIND_TO_DB_TYPE: dict[str, str] = {
    "postgres-sql": "postgres",
    "mongodb-aggregate": "mongodb",
    "sqlite-sql": "sqlite",
    "duckdb_bridge_sql": "duckdb",
}


def db_type_from_kind(kind: str) -> str:
    """Map a tool ``kind`` (from tools.yaml) to a canonical db_type string.

    Returns ``"unknown"`` for unrecognised kinds.
    """
    return _KIND_TO_DB_TYPE.get(kind, "unknown")


def validate_db_url(url: str, db_type: str) -> bool:
    """Basic format validation for a database connection URL.

    Checks that the URL is non-empty and uses an expected scheme for the
    given *db_type*.  This is a sanity check, not a full URI parser.
    """
    if not url:
        return False

    expected_schemes: dict[str, list[str]] = {
        "postgres": ["postgresql://", "postgres://"],
        "mongodb": ["mongodb://", "mongodb+srv://"],
        "sqlite": ["./", "/", "file:"],
        "duckdb": ["http://", "https://", "./", "/"],
    }
    schemes = expected_schemes.get(db_type, [])
    if not schemes:
        return False

    return any(url.startswith(s) for s in schemes)


# ---------------------------------------------------------------------------
# SEC-03: SQL sanitization for safe logging
# ---------------------------------------------------------------------------

_STRING_LITERAL_RE = re.compile(r"'[^']*'")
_NUMERIC_RE = re.compile(r"\b\d+\b")


def sanitize_sql_for_log(sql: str, max_length: int = 100) -> str:
    """Truncate and redact SQL for safe logging.

    - Truncates to *max_length* characters
    - Replaces string literals (``'...'``) with ``<STR>``
    - Replaces standalone numbers with ``<NUM>``
    """
    if not sql:
        return ""
    truncated = sql[:max_length]
    sanitized = _STRING_LITERAL_RE.sub("<STR>", truncated)
    sanitized = _NUMERIC_RE.sub("<NUM>", sanitized)
    if len(sql) > max_length:
        sanitized += "..."
    return sanitized
