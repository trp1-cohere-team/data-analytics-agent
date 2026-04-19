"""Failure classification for tool invocation errors.

FR-04: Classify failures into exactly one of 4 categories.
Maps DuckDB bridge ``error_type`` field to failure categories.
PBT-03: classify() ALWAYS returns a valid FailureDiagnosis — never raises, never returns None.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agent.data_agent.types import FailureDiagnosis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DuckDB bridge error_type → category mapping (FR-03b / FR-04)
# ---------------------------------------------------------------------------

_BRIDGE_ERROR_TYPE_MAP: dict[str, str] = {
    "policy": "db-type",
    "config": "db-type",
    "query": "query",
    "timeout": "db-type",
}

# ---------------------------------------------------------------------------
# Pattern-based classification rules
# ---------------------------------------------------------------------------

_QUERY_PATTERNS = re.compile(
    r"syntax|parse\s*error|unknown\s+column|unknown\s+table|"
    r"no\s+such\s+column|no\s+such\s+table|ambiguous|"
    r"sql\s*error|invalid\s+identifier|unrecognized",
    re.IGNORECASE,
)

_JOIN_KEY_PATTERNS = re.compile(
    r"join.*key|foreign\s+key|column.*mismatch|"
    r"join.*mismatch|referential|"
    r"cannot.*join|invalid.*join",
    re.IGNORECASE,
)

_DB_TYPE_PATTERNS = re.compile(
    r"unsupported|wrong\s+database|wrong\s+db|"
    r"timeout|timed?\s*out|connection\s*(refused|error|reset)|"
    r"not\s+available|unreachable|"
    r"read.only.violation|only\s+select",
    re.IGNORECASE,
)

_DATA_QUALITY_PATTERNS = re.compile(
    r"empty\s+result|no\s+rows|null|none\s+returned|"
    r"encoding|format.*error|data.*type.*mismatch|"
    r"unexpected.*type|truncat",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Suggested fixes per category
# ---------------------------------------------------------------------------

_SUGGESTED_FIXES: dict[str, str] = {
    "query": "Review and rewrite the query with correct syntax, table names, and column names.",
    "join-key": "Check the database schema for correct join columns and foreign key relationships.",
    "db-type": "Verify the correct database tool is selected and the service is available.",
    "data-quality": "Verify that the expected data exists, check data formats and encoding.",
}


def classify(
    error: str,
    context: Optional[dict] = None,
) -> FailureDiagnosis:
    """Classify a tool invocation failure into one of 4 categories.

    **Never raises an exception.  Never returns None.**

    Parameters
    ----------
    error : str
        The error message or description from the failed invocation.
    context : dict | None
        Optional context with ``error_type`` (from DuckDB bridge) or
        other metadata.

    Returns
    -------
    FailureDiagnosis
        Always contains a valid ``category`` in
        ``{"query", "join-key", "db-type", "data-quality"}``.
    """
    ctx = context or {}
    error_str = str(error) if error else ""

    try:
        # 1. Check DuckDB bridge error_type mapping first
        bridge_error_type = ctx.get("error_type", "")
        if bridge_error_type and bridge_error_type in _BRIDGE_ERROR_TYPE_MAP:
            category = _BRIDGE_ERROR_TYPE_MAP[bridge_error_type]
            return FailureDiagnosis(
                category=category,
                explanation=f"DuckDB bridge error_type='{bridge_error_type}' mapped to '{category}'.",
                suggested_fix=_SUGGESTED_FIXES[category],
                original_error=error_str,
            )

        # 2. Pattern-match against error string
        if _JOIN_KEY_PATTERNS.search(error_str):
            category = "join-key"
        elif _DB_TYPE_PATTERNS.search(error_str):
            category = "db-type"
        elif _DATA_QUALITY_PATTERNS.search(error_str):
            category = "data-quality"
        elif _QUERY_PATTERNS.search(error_str):
            category = "query"
        else:
            # 3. Default fallback
            category = "query"

        return FailureDiagnosis(
            category=category,
            explanation=f"Error classified as '{category}' based on pattern matching.",
            suggested_fix=_SUGGESTED_FIXES[category],
            original_error=error_str,
        )

    except Exception as exc:
        # Absolute safety net — never raise, never return None
        logger.warning("classify: unexpected error during classification: %s", exc)
        return FailureDiagnosis(
            category="query",
            explanation=f"Classification failed with internal error; defaulting to 'query'. ({exc})",
            suggested_fix=_SUGGESTED_FIXES["query"],
            original_error=error_str,
        )
