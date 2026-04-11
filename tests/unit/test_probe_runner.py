"""Unit tests for probes/probe_runner.py.

All tests mock the HTTP agent call — no live server required.

Covers:
- load_probes: parses probes.md, returns correct count and types
- score_response: null/empty/low-confidence/normal paths
- score_post_fix_response: null/empty/normal paths
- extract_error_signal: finds first error observation, None when clean
- count_correction_attempts: counts 'correct'/'retry' actions
- run_probe: records pre-fix score, returns updated ProbeEntry
- run_post_fix: post_fix_score >= threshold sets pass=True
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.models import ProbeEntry
from probes.probe_runner import (
    _PROBE_PASS_THRESHOLD,
    count_correction_attempts,
    extract_error_signal,
    load_probes,
    run_post_fix,
    run_probe,
    score_post_fix_response,
    score_response,
)

# ---------------------------------------------------------------------------
# Fixture: path to the real probes.md in the repo
# ---------------------------------------------------------------------------

_PROBES_MD = Path(__file__).parents[2] / "probes" / "probes.md"


# ---------------------------------------------------------------------------
# load_probes
# ---------------------------------------------------------------------------

class TestLoadProbes:
    def test_loads_from_probes_md(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        assert len(probes) == 15

    def test_all_entries_are_probe_entry(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        for p in probes:
            assert isinstance(p, ProbeEntry)

    def test_categories_present(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        categories = {p.category for p in probes}
        assert "ROUTING" in categories
        assert "JOIN_KEY" in categories
        assert "TEXT_EXTRACT" in categories
        assert "DOMAIN_GAP" in categories

    def test_routing_probe_count(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        routing = [p for p in probes if p.category == "ROUTING"]
        assert len(routing) == 4

    def test_join_key_probe_count(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        jk = [p for p in probes if p.category == "JOIN_KEY"]
        assert len(jk) == 4

    def test_probe_fields_populated(self):
        if not _PROBES_MD.exists():
            pytest.skip("probes/probes.md not found")
        probes = load_probes(_PROBES_MD)
        for p in probes:
            assert p.id
            assert p.category
            assert p.query
            assert p.expected_failure_mode
            assert p.fix_applied

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_probes("nonexistent/path/probes.md")


# ---------------------------------------------------------------------------
# score_response
# ---------------------------------------------------------------------------

class TestScoreResponse:
    def test_empty_dict_returns_zero(self):
        assert score_response({}, "SOME_FAILURE") == 0.0

    def test_none_answer_returns_zero(self):
        assert score_response({"answer": None, "confidence": 0.9}, "X") == 0.0

    def test_empty_string_answer_returns_zero(self):
        assert score_response({"answer": "", "confidence": 0.9}, "X") == 0.0

    def test_empty_list_answer_returns_zero(self):
        assert score_response({"answer": [], "confidence": 0.9}, "X") == 0.0

    def test_low_confidence_returns_confidence(self):
        score = score_response({"answer": "some answer", "confidence": 0.2}, "X")
        assert score == round(0.2, 2)

    def test_ok_confidence_capped_at_half(self):
        score = score_response({"answer": "some answer", "confidence": 0.9}, "X")
        assert score <= 0.5

    def test_missing_confidence_treated_as_zero(self):
        assert score_response({"answer": "x"}, "X") == 0.0


# ---------------------------------------------------------------------------
# score_post_fix_response
# ---------------------------------------------------------------------------

class TestScorePostFixResponse:
    def test_empty_dict_returns_zero(self):
        assert score_post_fix_response({}) == 0.0

    def test_none_answer_returns_zero(self):
        assert score_post_fix_response({"answer": None, "confidence": 0.9}) == 0.0

    def test_high_confidence_returns_confidence(self):
        score = score_post_fix_response({"answer": "42", "confidence": 0.95})
        assert score == round(0.95, 2)

    def test_pass_threshold_boundary(self):
        # At threshold → pass
        score = score_post_fix_response({"answer": "x", "confidence": _PROBE_PASS_THRESHOLD})
        assert score >= _PROBE_PASS_THRESHOLD


# ---------------------------------------------------------------------------
# extract_error_signal
# ---------------------------------------------------------------------------

class TestExtractErrorSignal:
    def test_no_errors_returns_none(self):
        trace = [
            {"action": "query_database", "observation": "rows returned: 5"},
            {"action": "FINAL_ANSWER", "observation": "done"},
        ]
        assert extract_error_signal(trace) is None

    def test_finds_error_observation(self):
        trace = [
            {"action": "query_database", "observation": "Connection error: timeout"},
        ]
        signal = extract_error_signal(trace)
        assert signal is not None
        assert "error" in signal.lower()

    def test_finds_failed_observation(self):
        trace = [{"action": "x", "observation": "Query failed: missing table"}]
        signal = extract_error_signal(trace)
        assert signal is not None

    def test_capped_at_500_chars(self):
        trace = [{"action": "x", "observation": "error " + "x" * 600}]
        signal = extract_error_signal(trace)
        assert signal is not None
        assert len(signal) <= 500

    def test_returns_first_error(self):
        trace = [
            {"action": "a", "observation": "first error here"},
            {"action": "b", "observation": "second exception here"},
        ]
        signal = extract_error_signal(trace)
        assert "first" in signal


# ---------------------------------------------------------------------------
# count_correction_attempts
# ---------------------------------------------------------------------------

class TestCountCorrectionAttempts:
    def test_no_corrections_returns_zero(self):
        trace = [{"action": "query_database"}, {"action": "FINAL_ANSWER"}]
        assert count_correction_attempts(trace) == 0

    def test_counts_correct_actions(self):
        trace = [
            {"action": "correct_syntax"},
            {"action": "correct_join_key"},
            {"action": "FINAL_ANSWER"},
        ]
        assert count_correction_attempts(trace) == 2

    def test_counts_retry_actions(self):
        trace = [{"action": "retry_query"}, {"action": "retry_query"}]
        assert count_correction_attempts(trace) == 2

    def test_mixed_actions(self):
        trace = [
            {"action": "correct_format"},
            {"action": "query_database"},
            {"action": "retry_query"},
        ]
        assert count_correction_attempts(trace) == 2


# ---------------------------------------------------------------------------
# run_probe (mocked HTTP)
# ---------------------------------------------------------------------------

def _make_probe(probe_id: str = "TEST-001") -> ProbeEntry:
    return ProbeEntry(
        id=probe_id,
        category="ROUTING",
        query="How many orders in California?",
        description="Test probe",
        expected_failure_mode="routes to wrong DB",
        db_types_involved=["postgres", "sqlite"],
        fix_applied="KB entry added",
        error_signal=None,
        correction_attempt_count=None,
        observed_agent_response=None,
        pre_fix_score=None,
        post_fix_score=None,
        post_fix_pass=None,
    )


class TestRunProbe:
    def test_run_probe_records_pre_fix_score(self):
        response = {
            "answer": None,
            "confidence": 0.0,
            "query_trace": [],
        }
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_probe(_make_probe(), "http://localhost:8000")
        assert result.pre_fix_score == 0.0

    def test_run_probe_records_error_signal(self):
        response = {
            "answer": None,
            "confidence": 0.0,
            "query_trace": [{"action": "query_db", "observation": "error: table not found"}],
        }
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_probe(_make_probe(), "http://localhost:8000")
        assert result.error_signal is not None
        assert "error" in result.error_signal.lower()

    def test_run_probe_records_correction_count(self):
        response = {
            "answer": "x",
            "confidence": 0.4,
            "query_trace": [
                {"action": "correct_syntax", "observation": "fixed"},
                {"action": "retry_query", "observation": "retried"},
            ],
        }
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_probe(_make_probe(), "http://localhost:8000")
        assert result.correction_attempt_count == 2

    def test_run_probe_returns_probe_entry(self):
        response = {"answer": None, "confidence": 0.0, "query_trace": []}
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_probe(_make_probe(), "http://localhost:8000")
        assert isinstance(result, ProbeEntry)


class TestRunPostFix:
    def test_high_score_sets_pass_true(self):
        response = {"answer": "42 orders", "confidence": 0.95, "query_trace": []}
        probe = _make_probe()
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_post_fix(probe, "http://localhost:8000")
        assert result.post_fix_pass is True
        assert result.post_fix_score >= _PROBE_PASS_THRESHOLD

    def test_low_score_sets_pass_false(self):
        response = {"answer": "something", "confidence": 0.3, "query_trace": []}
        probe = _make_probe()
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_post_fix(probe, "http://localhost:8000")
        assert result.post_fix_pass is False

    def test_none_answer_sets_pass_false(self):
        response = {"answer": None, "confidence": 0.99, "query_trace": []}
        probe = _make_probe()
        with patch("probes.probe_runner._call_agent", return_value=response):
            result = run_post_fix(probe, "http://localhost:8000")
        assert result.post_fix_pass is False
