"""Hypothesis strategy factory for U5/U3 property-based tests.

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
    # U5 invariants
    "PBT-U5-01": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-02": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U5-03": settings(max_examples=100, deadline=timedelta(milliseconds=200)),
    "PBT-U5-04": settings(max_examples=100, deadline=timedelta(milliseconds=500)),
    "PBT-U5-05": settings(max_examples=150, deadline=timedelta(milliseconds=200)),
    # U1 invariants
    "PBT-U1-01": settings(max_examples=300, deadline=timedelta(milliseconds=200)),
    "PBT-U1-02": settings(max_examples=200, deadline=timedelta(milliseconds=200)),
    # U3 invariants
    "PBT-U3-01": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
    "PBT-U3-02": settings(max_examples=100, deadline=timedelta(milliseconds=2000)),
    "PBT-U3-03": settings(max_examples=150, deadline=timedelta(milliseconds=1000)),
    "PBT-U3-04": settings(max_examples=100, deadline=timedelta(milliseconds=2000)),
    "PBT-U3-05": settings(max_examples=150, deadline=timedelta(milliseconds=500)),
    "PBT-U3-06": settings(max_examples=200, deadline=timedelta(milliseconds=500)),
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
# U1 strategies — ExecutionFailure (PBT-U1-01)
# ---------------------------------------------------------------------------

@st.composite
def execution_failures(draw: st.DrawFn) -> Any:
    """Generate a valid ExecutionFailure for CorrectionEngine PBT tests."""
    from agent.models import ExecutionFailure
    db_types = ["postgres", "sqlite", "mongodb", "duckdb"]
    error_types = ["timeout", "connection_error", "rate_limit", "auth_error",
                   "schema_error", "data_type_error", "query_error", "unknown"]
    return ExecutionFailure(
        sub_query_id=str(draw(st.uuids())),
        db_type=draw(st.sampled_from(db_types)),
        error_message=draw(st.text(min_size=1, max_size=300, alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")))),
        error_type=draw(st.sampled_from(error_types)),
    )


# ---------------------------------------------------------------------------
# U3 strategies — SessionTranscript and SessionMemory (PBT-U3-04 through -06)
# ---------------------------------------------------------------------------

@st.composite
def trace_steps(draw: st.DrawFn) -> Any:
    """Generate a valid TraceStep for use inside SessionTranscript histories."""
    from agent.models import TraceStep
    actions = ["query_database", "search_kb", "extract_from_text", "resolve_join_keys", "FINAL_ANSWER"]
    return TraceStep(
        iteration=draw(st.integers(min_value=0, max_value=20)),
        thought=draw(st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))),
        action=draw(st.sampled_from(actions)),
        action_input={},
        observation=draw(st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))),
        timestamp=draw(st.floats(min_value=1_600_000_000.0, max_value=2_000_000_000.0)),
    )


@st.composite
def session_transcripts(draw: st.DrawFn) -> Any:
    """Generate a valid SessionTranscript with realistic fields.

    PBT-U3-04 / PBT-U3-05 / PBT-U3-06 invariant strategy.
    session_id is a UUID string, timestamp is a valid epoch float,
    history is a list[TraceStep], summary is a non-empty string.
    """
    from agent.models import SessionTranscript
    history_steps = draw(st.lists(trace_steps(), min_size=0, max_size=10))
    return SessionTranscript(
        session_id=str(draw(st.uuids())),
        timestamp=draw(st.floats(min_value=1_600_000_000.0, max_value=2_000_000_000.0)),
        history=history_steps,
        summary=draw(st.text(min_size=1, max_size=500, alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")))),
    )


@st.composite
def session_memory_objects(draw: st.DrawFn) -> Any:
    """Generate a valid SessionMemory with realistic nested structures.

    PBT-U3-06 round-trip strategy.
    """
    from agent.models import SessionMemory

    def pattern_entry(d: st.DrawFn) -> dict[str, Any]:
        return {
            "session_id": str(d(st.uuids())),
            "summary": d(st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))),
        }

    def correction_entry(d: st.DrawFn) -> dict[str, Any]:
        return {
            "session_id": str(d(st.uuids())),
            "corrections": d(st.lists(st.fixed_dictionaries({
                "iteration": st.integers(min_value=0, max_value=20),
                "action": st.sampled_from(["correct_query", "fix_syntax"]),
                "observation": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
            }), min_size=0, max_size=3)),
        }

    patterns = draw(st.lists(st.builds(pattern_entry, st.just(draw)), min_size=0, max_size=5))
    corrections = draw(st.lists(st.builds(correction_entry, st.just(draw)), min_size=0, max_size=5))
    preferences = draw(st.dictionaries(
        st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
        st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
        min_size=0, max_size=5,
    ))
    return SessionMemory(
        successful_patterns=patterns,
        user_preferences=preferences,
        query_corrections=corrections,
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
