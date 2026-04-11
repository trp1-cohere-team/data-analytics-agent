"""Unit tests for ExactMatchScorer and LLMJudgeScorer in eval/harness.py."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given

from agent.models import JudgeVerdict
from eval.harness import ExactMatchScorer, LLMJudgeScorer
from tests.unit.strategies import INVARIANT_SETTINGS, numeric_values


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# ExactMatchScorer — numeric
# ---------------------------------------------------------------------------

class TestExactMatchScorerNumeric:
    def test_integer_self_match(self):
        assert ExactMatchScorer.score("42", 42) is True

    def test_negative_integer_self_match(self):
        assert ExactMatchScorer.score("-100", -100) is True

    def test_float_self_match(self):
        assert ExactMatchScorer.score("3.14", 3.14) is True

    def test_within_1_percent_tolerance_passes(self):
        # 100 and 100.5 differ by 0.5% — within 1%
        assert ExactMatchScorer.score("100.5", 100) is True

    def test_beyond_1_percent_tolerance_fails(self):
        # 100 and 102 differ by 2% — outside 1%
        assert ExactMatchScorer.score("102", 100) is False

    def test_non_parseable_string_fails(self):
        assert ExactMatchScorer.score("not-a-number", 42) is False

    def test_zero_expected_uses_denominator_guard(self):
        # expected=0: denom = max(0, 1.0) = 1.0; "0.005" is within 1%
        assert ExactMatchScorer.score("0.005", 0) is True

    def test_zero_expected_large_value_fails(self):
        # "0.5" vs 0: abs(0.5 - 0) / 1.0 = 0.5 > 0.01
        assert ExactMatchScorer.score("0.5", 0) is False


# ---------------------------------------------------------------------------
# ExactMatchScorer — string
# ---------------------------------------------------------------------------

class TestExactMatchScorerString:
    def test_case_insensitive_match_passes(self):
        assert ExactMatchScorer.score("Revenue", "revenue") is True

    def test_whitespace_stripped_passes(self):
        assert ExactMatchScorer.score("  hello  ", "hello") is True

    def test_different_strings_fail(self):
        assert ExactMatchScorer.score("foo", "bar") is False

    def test_empty_strings_match(self):
        assert ExactMatchScorer.score("", "") is True


# ---------------------------------------------------------------------------
# ExactMatchScorer — list
# ---------------------------------------------------------------------------

class TestExactMatchScorerList:
    def test_list_element_wise_match_passes(self):
        assert ExactMatchScorer.score('["alpha", "beta"]', ["alpha", "beta"]) is True

    def test_list_case_insensitive_elements_pass(self):
        assert ExactMatchScorer.score('["Alpha"]', ["alpha"]) is True

    def test_list_wrong_length_fails(self):
        assert ExactMatchScorer.score('["a"]', ["a", "b"]) is False

    def test_list_non_parseable_fails(self):
        assert ExactMatchScorer.score("not a list", ["a"]) is False

    def test_list_numeric_elements_with_tolerance(self):
        assert ExactMatchScorer.score('[100, 200]', [100, 200]) is True


# ---------------------------------------------------------------------------
# LLMJudgeScorer
# ---------------------------------------------------------------------------

class TestLLMJudgeScorer:
    def _make_client(self, content: str) -> MagicMock:
        mock_msg = MagicMock()
        mock_msg.content = content
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=mock_resp)
        return client

    def test_valid_json_response_returns_correct_verdict(self):
        payload = json.dumps({"passed": True, "rationale": "answer is correct", "confidence": 0.92})
        client = self._make_client(payload)
        verdict = _run(LLMJudgeScorer.score("What is revenue?", "1000", 1000, client))
        assert isinstance(verdict, JudgeVerdict)
        assert verdict.passed is True
        assert verdict.confidence == pytest.approx(0.92)
        assert verdict.rationale == "answer is correct"

    def test_judge_passed_false_returned_correctly(self):
        payload = json.dumps({"passed": False, "rationale": "wrong value", "confidence": 0.85})
        client = self._make_client(payload)
        verdict = _run(LLMJudgeScorer.score("What is revenue?", "999", 1000, client))
        assert verdict.passed is False

    def test_malformed_json_returns_parse_error_verdict(self):
        client = self._make_client("this is not json at all")
        verdict = _run(LLMJudgeScorer.score("What is revenue?", "1000", 1000, client))
        assert isinstance(verdict, JudgeVerdict)
        assert verdict.passed is False
        assert verdict.rationale == "judge_parse_error"
        assert verdict.confidence == pytest.approx(0.0)

    def test_missing_passed_field_returns_parse_error_verdict(self):
        # JSON valid but missing required "passed" key
        payload = json.dumps({"rationale": "ok", "confidence": 0.9})
        client = self._make_client(payload)
        verdict = _run(LLMJudgeScorer.score("Q?", "A", "A", client))
        assert verdict.passed is False
        assert verdict.rationale == "judge_parse_error"

    def test_llm_api_exception_returns_parse_error_verdict(self):
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))
        verdict = _run(LLMJudgeScorer.score("Q?", "A", "A", client))
        assert verdict.passed is False
        assert verdict.rationale == "judge_parse_error"


# ---------------------------------------------------------------------------
# PBT-U4-01: ExactMatch self-consistency
# ---------------------------------------------------------------------------

@given(pair=numeric_values())
@INVARIANT_SETTINGS["PBT-U4-01"]
def test_exact_match_self_consistency(pair):
    """PBT-U4-01: ExactMatchScorer.score(str(x), x) == True for any numeric x.

    A value must always match its own string representation within 1% tolerance.
    500 examples — pure CPU, deadline 50ms per example.
    """
    value, str_repr = pair
    result = ExactMatchScorer.score(str_repr, value)
    assert result is True, (
        f"Self-match failed: score({str_repr!r}, {value!r}) returned False"
    )
