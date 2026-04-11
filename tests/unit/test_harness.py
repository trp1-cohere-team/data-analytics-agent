"""Unit tests for EvaluationHarness sub-components in eval/harness.py."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from hypothesis import given

from agent.models import BenchmarkResult, DABQuery, RegressionResult
from eval.harness import (
    BenchmarkRunner,
    EvaluationHarness,
    RegressionSuite,
    ScoreLog,
)
from tests.unit.strategies import INVARIANT_SETTINGS, benchmark_results


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_result(
    run_id: str,
    pass_at_1: float,
    per_query: dict | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        timestamp=time.time(),
        agent_url="http://localhost:8000",
        n_trials=1,
        total_queries=len(per_query or {}),
        pass_at_1=pass_at_1,
        per_query_scores=per_query or {},
    )


def _make_query(expected=42, qid="q1") -> DABQuery:
    return DABQuery(id=qid, question="What is 42?", expected_answer=expected, category="NUMERIC")


# ---------------------------------------------------------------------------
# ScoreLog — AppendOnlyScoreWriter
# ---------------------------------------------------------------------------

class TestScoreLog:
    def test_load_last_returns_none_when_file_absent(self, tmp_path):
        assert ScoreLog.load_last(tmp_path) is None

    def test_load_last_returns_none_on_empty_file(self, tmp_path):
        (tmp_path / "score_log.jsonl").write_text("", encoding="utf-8")
        assert ScoreLog.load_last(tmp_path) is None

    def test_append_then_load_last_returns_appended_entry(self, tmp_path):
        result = _make_result("run-1", 0.8)
        ScoreLog.append(result, tmp_path)
        loaded = ScoreLog.load_last(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "run-1"

    def test_multiple_appends_load_last_returns_final_entry(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.7), tmp_path)
        ScoreLog.append(_make_result("run-2", 0.9), tmp_path)
        loaded = ScoreLog.load_last(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "run-2"

    def test_load_last_before_skips_given_run_id(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.7), tmp_path)
        ScoreLog.append(_make_result("run-2", 0.9), tmp_path)
        prev = ScoreLog.load_last_before("run-2", tmp_path)
        assert prev is not None
        assert prev.run_id == "run-1"

    def test_load_last_before_returns_none_when_only_current_run_exists(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.8), tmp_path)
        assert ScoreLog.load_last_before("run-1", tmp_path) is None


# ---------------------------------------------------------------------------
# RegressionSuite
# ---------------------------------------------------------------------------

class TestRegressionSuite:
    def test_no_baseline_auto_passes(self, tmp_path):
        current = _make_result("run-1", 0.8)
        ScoreLog.append(current, tmp_path)
        reg = RegressionSuite.check(current, tmp_path)
        assert isinstance(reg, RegressionResult)
        assert reg.passed is True
        assert reg.previous_score == pytest.approx(0.0)
        assert reg.delta == pytest.approx(0.8)
        assert reg.failed_queries == []

    def test_improvement_passes_regression_gate(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.7), tmp_path)
        current = _make_result("run-2", 0.9)
        ScoreLog.append(current, tmp_path)
        reg = RegressionSuite.check(current, tmp_path)
        assert reg.passed is True
        assert reg.delta == pytest.approx(0.2)

    def test_equal_score_passes_regression_gate(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.8), tmp_path)
        current = _make_result("run-2", 0.8)
        ScoreLog.append(current, tmp_path)
        reg = RegressionSuite.check(current, tmp_path)
        assert reg.passed is True  # >= not > (strict pass/fail boundary)

    def test_any_drop_fails_regression_gate(self, tmp_path):
        ScoreLog.append(_make_result("run-1", 0.9), tmp_path)
        current = _make_result("run-2", 0.89)
        ScoreLog.append(current, tmp_path)
        reg = RegressionSuite.check(current, tmp_path)
        assert reg.passed is False

    def test_failed_queries_lists_only_newly_regressed(self, tmp_path):
        # q1 was passing, q2 was already failing
        prev = _make_result("run-1", 0.5, {"q1": 1.0, "q2": 0.0})
        ScoreLog.append(prev, tmp_path)
        current = _make_result("run-2", 0.0, {"q1": 0.0, "q2": 0.0})
        ScoreLog.append(current, tmp_path)
        reg = RegressionSuite.check(current, tmp_path)
        assert "q1" in reg.failed_queries   # was passing, now failing
        assert "q2" not in reg.failed_queries  # was already failing


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------

class TestBenchmarkRunner:
    def _mock_session(self, answer: str) -> MagicMock:
        resp = AsyncMock()
        resp.json = AsyncMock(return_value={
            "answer": answer,
            "confidence": 0.9,
            "session_id": "s1",
        })
        resp.raise_for_status = MagicMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        return session

    def _make_llm_client(self) -> MagicMock:
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock()
        return client

    def test_exact_match_pass_skips_llm_judge(self, tmp_path):
        """WaterfallScorer: ExactMatch pass -> LLMJudge never called."""
        runner = BenchmarkRunner()
        session = self._mock_session("42")
        query = _make_query(expected=42)
        sem = asyncio.Semaphore(5)
        llm_client = self._make_llm_client()

        score = _run(runner.run_query(
            query, 1, "run-1", tmp_path, session, sem, llm_client, "http://localhost:8000"
        ))

        assert score == pytest.approx(1.0)
        llm_client.chat.completions.create.assert_not_called()

    def test_exact_match_fail_calls_llm_judge(self, tmp_path):
        """WaterfallScorer: ExactMatch fail -> LLMJudge is called."""
        runner = BenchmarkRunner()
        session = self._mock_session("completely wrong")
        query = _make_query(expected=42)
        sem = asyncio.Semaphore(5)

        verdict_content = json.dumps({"passed": True, "rationale": "close enough", "confidence": 0.8})
        verdict_resp = MagicMock()
        verdict_resp.choices = [MagicMock()]
        verdict_resp.choices[0].message.content = verdict_content

        llm_client = MagicMock()
        llm_client.chat = MagicMock()
        llm_client.chat.completions = MagicMock()
        llm_client.chat.completions.create = AsyncMock(return_value=verdict_resp)

        score = _run(runner.run_query(
            query, 1, "run-2", tmp_path, session, sem, llm_client, "http://localhost:8000"
        ))

        assert score == pytest.approx(1.0)  # judge said passed
        llm_client.chat.completions.create.assert_called_once()

    def test_http_error_recorded_as_failed_no_exception_raised(self, tmp_path):
        """FailSafeTrialRunner: HTTP error -> passed=False, no exception propagated."""
        runner = BenchmarkRunner()
        resp = MagicMock()
        resp.raise_for_status = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        query = _make_query()
        sem = asyncio.Semaphore(5)
        llm_client = self._make_llm_client()

        score = _run(runner.run_query(
            query, 1, "run-http-err", tmp_path, session, sem, llm_client, "http://localhost:8000"
        ))

        assert score == pytest.approx(0.0)  # failed trial
        # no exception propagated — run completed normally


# ---------------------------------------------------------------------------
# EvaluationHarness
# ---------------------------------------------------------------------------

class TestEvaluationHarness:
    def _setup_mock_session(self, answer: str):
        resp = AsyncMock()
        resp.json = AsyncMock(return_value={
            "answer": answer, "confidence": 0.9, "session_id": "s1",
        })
        resp.raise_for_status = MagicMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session_inst = MagicMock()
        session_inst.post = MagicMock(return_value=resp)
        session_inst.__aenter__ = AsyncMock(return_value=session_inst)
        session_inst.__aexit__ = AsyncMock(return_value=False)
        return session_inst

    def test_run_returns_benchmark_result_with_correct_pass_at_1(self, tmp_path):
        query = _make_query(expected=42)
        session_inst = self._setup_mock_session("42")

        with patch("eval.harness.aiohttp.ClientSession", return_value=session_inst), \
             patch("eval.harness.openai.AsyncOpenAI"):
            harness = EvaluationHarness()
            result, _ = _run(harness.run([query], "http://localhost:8000", n_trials=1, results_dir=tmp_path))

        assert isinstance(result, BenchmarkResult)
        assert result.pass_at_1 == pytest.approx(1.0)
        assert result.total_queries == 1

    def test_run_appends_to_score_log(self, tmp_path):
        query = _make_query(expected=42)
        session_inst = self._setup_mock_session("42")

        with patch("eval.harness.aiohttp.ClientSession", return_value=session_inst), \
             patch("eval.harness.openai.AsyncOpenAI"):
            harness = EvaluationHarness()
            _run(harness.run([query], "http://localhost:8000", n_trials=1, results_dir=tmp_path))

        log_path = tmp_path / "score_log.jsonl"
        assert log_path.exists()
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# PBT-U4-02: ScoreLog round-trip integrity
# ---------------------------------------------------------------------------

@given(result=benchmark_results())
@INVARIANT_SETTINGS["PBT-U4-02"]
def test_score_log_round_trip(result):
    """PBT-U4-02: ScoreLog.append(r) then load_last() returns entry with same run_id.

    Invariant: what is appended can always be read back.
    200 examples — file I/O round-trip, deadline 500ms per example.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        ScoreLog.append(result, tmp_path)
        loaded = ScoreLog.load_last(tmp_path)

    assert loaded is not None, "load_last() returned None after append"
    assert loaded.run_id == result.run_id, (
        f"run_id mismatch: expected {result.run_id!r}, got {loaded.run_id!r}"
    )
