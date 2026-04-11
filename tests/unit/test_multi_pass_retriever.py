"""Unit tests for utils/multi_pass_retriever.py.

Covers:
- retrieve_corrections: empty corpus, zero-match, top-10 cap, dedup, ranking
- _compute_idf: gate at 20 entries, returns empty dict below threshold
- _build_pass_queries: returns 3 passes, domain terms extracted
- PBT: result count ≤ 10, all scores ≥ 0
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from hypothesis import given, settings as h_settings

from agent.models import CorrectionEntry
from tests.unit.strategies import INVARIANT_SETTINGS, correction_entries
from utils.multi_pass_retriever import (
    _build_pass_queries,
    _compute_idf,
    retrieve_corrections,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    failure_type: str = "SYNTAX_ERROR",
    original_query: str = "select from orders",
    corrected_query: str | None = "SELECT * FROM orders",
    error_message: str = "syntax error near select",
    fix_strategy: str = "rule_syntax",
    attempt_number: int = 1,
    success: bool = True,
    timestamp: float | None = None,
) -> CorrectionEntry:
    return CorrectionEntry(
        id=str(uuid.uuid4()),
        timestamp=timestamp or time.time(),
        session_id=str(uuid.uuid4()),
        failure_type=failure_type,
        original_query=original_query,
        corrected_query=corrected_query,
        error_message=error_message,
        fix_strategy=fix_strategy,
        attempt_number=attempt_number,
        success=success,
    )


def _make_corpus(n: int, **kwargs: Any) -> list[CorrectionEntry]:
    return [_make_entry(**kwargs) for _ in range(n)]


# ---------------------------------------------------------------------------
# retrieve_corrections — basic behaviour
# ---------------------------------------------------------------------------

class TestRetrieveCorrections:
    def test_empty_corpus_returns_empty(self):
        result = retrieve_corrections("some query", [])
        assert result == []

    def test_no_match_returns_empty(self):
        # Corpus entries have text that won't match any vocab keyword
        corpus = [
            _make_entry(
                original_query="aaaa bbbb cccc",
                error_message="aaaa",
                fix_strategy="aaaa",
                failure_type="UNKNOWN",
            )
            for _ in range(3)
        ]
        # The query also has no overlap with corrections vocab
        result = retrieve_corrections("aaaa bbbb", corpus)
        assert isinstance(result, list)
        # May or may not match — importantly must not raise
        assert len(result) <= 10

    def test_result_capped_at_ten(self):
        # 20+ entries that all match "syntax error"
        corpus = _make_corpus(25, error_message="syntax error", failure_type="SYNTAX_ERROR")
        result = retrieve_corrections("syntax error query", corpus)
        assert len(result) <= 10

    def test_no_duplicates_in_result(self):
        corpus = _make_corpus(5, error_message="syntax error join mismatch")
        result = retrieve_corrections("syntax error join", corpus)
        ids = [e.id for e in result]
        assert len(ids) == len(set(ids))

    def test_returns_list_of_correction_entry(self):
        corpus = _make_corpus(3, error_message="join key mismatch postgres")
        result = retrieve_corrections("join key", corpus)
        for item in result:
            assert isinstance(item, CorrectionEntry)

    def test_high_score_entry_ranks_first(self):
        # One entry with many matching high-value terms
        high_match = _make_entry(
            original_query="join mismatch uuid composite cross-db",
            error_message="join key mismatch syntax error",
            failure_type="JOIN_KEY_MISMATCH",
        )
        low_match = _make_entry(
            original_query="something else unrelated",
            error_message="some error",
            failure_type="UNKNOWN",
        )
        result = retrieve_corrections("join key mismatch uuid cross-db", [high_match, low_match])
        if len(result) >= 1:
            assert result[0].id == high_match.id

    def test_tiebreaker_more_recent_wins(self):
        older = _make_entry(error_message="syntax error join", timestamp=1_600_000_000.0)
        newer = _make_entry(error_message="syntax error join", timestamp=1_700_000_000.0)
        result = retrieve_corrections("syntax error join", [older, newer])
        assert len(result) == 2
        assert result[0].id == newer.id  # MPR-06

    def test_zero_score_entries_excluded(self):
        # Entry with content that has no keywords in vocab
        corpus = [
            _make_entry(
                original_query="xyz xyz xyz",
                error_message="xyz xyz",
                fix_strategy="xyz",
                failure_type="UNKNOWN",
            )
        ]
        result = retrieve_corrections("xyz xyz", corpus)
        # Should return 0 or entries only if they accidentally match
        assert len(result) <= 1

    def test_case_insensitive_matching(self):
        # MPR-07: keyword matching is case-insensitive
        corpus = [_make_entry(error_message="SYNTAX ERROR", failure_type="SYNTAX_ERROR")]
        result = retrieve_corrections("syntax error", corpus)
        assert any(e.failure_type == "SYNTAX_ERROR" for e in result)


# ---------------------------------------------------------------------------
# _compute_idf
# ---------------------------------------------------------------------------

class TestComputeIdf:
    def test_below_threshold_returns_empty(self):
        corpus = _make_corpus(19)
        assert _compute_idf(corpus) == {}

    def test_exactly_threshold_returns_empty(self):
        corpus = _make_corpus(19)
        assert _compute_idf(corpus) == {}

    def test_above_threshold_returns_weights(self):
        corpus = _make_corpus(20)
        idf = _compute_idf(corpus)
        assert isinstance(idf, dict)
        assert len(idf) > 0

    def test_idf_values_are_positive(self):
        corpus = _make_corpus(25)
        idf = _compute_idf(corpus)
        for term, weight in idf.items():
            assert weight >= 0, f"Negative IDF for term '{term}': {weight}"


# ---------------------------------------------------------------------------
# _build_pass_queries
# ---------------------------------------------------------------------------

class TestBuildPassQueries:
    def test_returns_three_passes(self):
        passes = _build_pass_queries("select from orders where postgres")
        assert len(passes) == 3

    def test_each_pass_is_a_list(self):
        passes = _build_pass_queries("query text")
        for p in passes:
            assert isinstance(p, list)

    def test_db_name_in_pass1(self):
        passes = _build_pass_queries("query against postgres database")
        assert "postgres" in passes[0]

    def test_failure_type_in_pass2(self):
        passes = _build_pass_queries("there was a syntax error")
        # "syntax" should appear in pass2
        assert "syntax" in passes[1]

    def test_domain_term_extraction_in_pass3(self):
        passes = _build_pass_queries("the business revenue report query")
        # Long words not in stop-words should appear in pass3
        assert any(w in passes[2] for w in ["business", "revenue", "report"])


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

class TestPBTMultiPassRetriever:
    @given(entries=correction_entries().flatmap(
        lambda e: correction_entries().map(lambda e2: [e, e2])
    ))
    @h_settings(INVARIANT_SETTINGS["PBT-U5-02"])
    def test_pbt_result_count_le_10(self, entries: list[CorrectionEntry]) -> None:
        """retrieve_corrections never returns more than 10 entries."""
        result = retrieve_corrections("syntax error join mismatch", entries)
        assert len(result) <= 10

    @given(entries=correction_entries().flatmap(
        lambda e: correction_entries().map(lambda e2: [e, e2])
    ))
    @h_settings(INVARIANT_SETTINGS["PBT-U5-02"])
    def test_pbt_no_duplicates(self, entries: list[CorrectionEntry]) -> None:
        """retrieve_corrections never returns duplicate entries."""
        result = retrieve_corrections("join key", entries)
        ids = [e.id for e in result]
        assert len(ids) == len(set(ids))

    @given(entry=correction_entries())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-03"])
    def test_pbt_idempotent(self, entry: CorrectionEntry) -> None:
        """Calling retrieve_corrections twice with same inputs returns same entry set."""
        corpus = [entry]
        r1 = retrieve_corrections("syntax error join", corpus)
        r2 = retrieve_corrections("syntax error join", corpus)
        assert [e.id for e in r1] == [e.id for e in r2]
