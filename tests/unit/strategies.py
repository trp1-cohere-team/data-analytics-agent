"""Hypothesis strategy factory for U5 property-based tests.

All custom @st.composite strategies and the InvariantRegistry are defined here.
Test files import from this module — never redefine strategies locally.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from hypothesis import settings
from hypothesis import strategies as st

from agent.models import JoinKeyFormat

# ---------------------------------------------------------------------------
# Hypothesis settings registry (PBT-U5-01 through PBT-U5-05)
# ---------------------------------------------------------------------------

INVARIANT_SETTINGS: dict[str, Any] = {
    "PBT-U5-01": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-02": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-03": settings(max_examples=100, deadline=timedelta(milliseconds=200)),
    "PBT-U5-04": settings(max_examples=100, deadline=timedelta(milliseconds=500)),
    "PBT-U5-05": settings(max_examples=150, deadline=timedelta(milliseconds=200)),
}


# ---------------------------------------------------------------------------
# Key value strategies
# ---------------------------------------------------------------------------

@st.composite
def integer_keys(draw: st.DrawFn, min_val: int = 1, max_val: int = 999_999) -> int:
    """Generate valid INTEGER format key values."""
    return draw(st.integers(min_value=min_val, max_value=max_val))


@st.composite
def prefixed_keys(
    draw: st.DrawFn,
    prefix: str | None = None,
    width: int | None = None,
) -> str:
    """Generate valid PREFIXED_STRING format key values (e.g. 'CUST-01234')."""
    p = prefix or draw(st.sampled_from(["CUST", "ORD", "ITEM", "TXN", "USR"]))
    w = width or draw(st.integers(min_value=1, max_value=8))
    n = draw(st.integers(min_value=0, max_value=10**w - 1))
    return f"{p}-{str(n).zfill(w)}"


@st.composite
def uuid_keys(draw: st.DrawFn) -> str:
    """Generate valid UUID format key values."""
    return str(draw(st.uuids()))


def strategy_for(fmt: JoinKeyFormat) -> st.SearchStrategy[Any]:
    """Return the appropriate strategy for a given JoinKeyFormat."""
    if fmt == JoinKeyFormat.INTEGER:
        return integer_keys()
    if fmt == JoinKeyFormat.PREFIXED_STRING:
        return prefixed_keys()
    if fmt == JoinKeyFormat.UUID:
        return uuid_keys()
    return st.just("UNKNOWN_VALUE")


@st.composite
def key_samples_with_majority(
    draw: st.DrawFn,
    primary_fmt: JoinKeyFormat,
    minority_fmts: list[JoinKeyFormat] | None = None,
    n: int | None = None,
) -> list[Any]:
    """Generate a list of key samples where primary_fmt is the strict majority."""
    size = n or draw(st.integers(min_value=3, max_value=20))
    majority_count = size // 2 + 1
    minority_count = size - majority_count

    majority = [draw(strategy_for(primary_fmt)) for _ in range(majority_count)]

    minority_pool = minority_fmts or [
        f for f in [JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING]
        if f != primary_fmt
    ]
    minority = [
        draw(strategy_for(draw(st.sampled_from(minority_pool))))
        for _ in range(minority_count)
    ]

    combined = majority + minority
    return draw(st.permutations(combined))


# ---------------------------------------------------------------------------
# CorrectionEntry strategy (for MultiPassRetriever PBT)
# ---------------------------------------------------------------------------

@st.composite
def correction_entries(draw: st.DrawFn) -> Any:
    """Generate a valid CorrectionEntry for MultiPassRetriever tests."""
    from agent.models import CorrectionEntry
    failure_types = ["SYNTAX_ERROR", "JOIN_KEY_MISMATCH", "WRONG_DB_TYPE", "DATA_QUALITY", "UNKNOWN"]
    fix_strategies = ["rule_syntax", "rule_join_key", "rule_db_type", "rule_null_guard", "llm_corrector"]
    return CorrectionEntry(
        id=str(draw(st.uuids())),
        timestamp=draw(st.floats(min_value=1_600_000_000.0, max_value=2_000_000_000.0)),
        session_id=str(draw(st.uuids())),
        failure_type=draw(st.sampled_from(failure_types)),
        original_query=draw(st.text(min_size=5, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))),
        corrected_query=draw(st.one_of(st.none(), st.text(min_size=5, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))))),
        error_message=draw(st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))),
        fix_strategy=draw(st.sampled_from(fix_strategies)),
        attempt_number=draw(st.integers(min_value=1, max_value=3)),
        success=draw(st.booleans()),
    )


# ---------------------------------------------------------------------------
# SQL expression validator
# ---------------------------------------------------------------------------

def validate_sql_expression(expr: str, source_column: str, db_type: str) -> bool:
    """Lightweight structural check — no DB engine required (PBT-U5-05).

    Verifies:
    1. No unresolved template placeholders ({...})
    2. Source column name is present in the expression
    3. Dialect-appropriate functions used (no LPAD in sqlite, no printf in postgres/duckdb)
    """
    assert "{" not in expr and "}" not in expr, f"Unresolved placeholder in: {expr}"
    assert source_column in expr, f"Source column '{source_column}' missing from: {expr}"
    if db_type == "sqlite":
        assert "LPAD" not in expr, f"SQLite: use printf, not LPAD — got: {expr}"
    if db_type in ("postgres", "duckdb"):
        assert "printf" not in expr, f"{db_type}: use LPAD, not printf — got: {expr}"
    return True
