"""Evaluation Harness — benchmarks The Oracle Forge against the DataAgentBench (DAB) dataset.

All sub-components are internal to this module.

Public API:
    EvaluationHarness.run(queries, agent_url, n_trials, results_dir)
        -> tuple[BenchmarkResult, RegressionResult]

NFR Patterns implemented:
    Pattern 1 — AppendOnlyScoreWriter  (ScoreLog.append uses "a" mode exclusively)
    Pattern 2 — SemaphoreThrottledCaller  (asyncio.Semaphore(_AGENT_CONCURRENCY))
    Pattern 3 — FailSafeTrialRunner  (HTTP errors -> passed=False, run continues)
    Pattern 4 — WaterfallScorer  (ExactMatch first; LLMJudge only on failure)

Security:
    SEC-U4-01: No query/answer content in log lines — metadata only
    SEC-U4-02: score_log.jsonl opened in "a" mode exclusively
    SEC-U4-03: API key consumed from settings; never written to any file
    SEC-U4-04: Trace files are write-once (ValueError on duplicate path)
    SEC-U4-05: Agent called via aiohttp JSON body — no shell interpolation
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
import openai

from agent.config import settings
from agent.models import BenchmarkResult, DABQuery, JudgeVerdict, RegressionResult

logger = logging.getLogger(__name__)

_AGENT_CONCURRENCY = 5  # Pattern 2: SemaphoreThrottledCaller

_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial benchmark evaluator. Your task is to determine if an "
    "AI agent answered a data analytics question correctly.\n\n"
    "Respond with ONLY valid JSON in this exact format:\n"
    '{"passed": <bool>, "rationale": "<1-2 sentences>", "confidence": <float 0-1>}\n\n'
    "Scoring criteria:\n"
    "- Numeric answers: accept if within 1% relative tolerance\n"
    "- String answers: accept case-insensitive, ignore surrounding whitespace\n"
    "- The agent's reasoning style or phrasing does not affect correctness"
)


# ---------------------------------------------------------------------------
# TrialRecord — ephemeral per-trial result
# ---------------------------------------------------------------------------

@dataclass
class TrialRecord:
    """One trial for one DAB query. Written to disk by QueryTraceRecorder."""
    query_id: str
    trial_index: int
    question: str
    agent_answer: str
    agent_confidence: float
    session_id: str
    elapsed_ms: float
    exact_match_passed: bool | None = None
    judge_verdict: JudgeVerdict | None = None
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "trial_index": self.trial_index,
            "question": self.question,
            "agent_answer": self.agent_answer,
            "agent_confidence": self.agent_confidence,
            "session_id": self.session_id,
            "elapsed_ms": self.elapsed_ms,
            "exact_match_passed": self.exact_match_passed,
            "judge_verdict": self.judge_verdict.model_dump() if self.judge_verdict else None,
            "passed": self.passed,
        }


# ---------------------------------------------------------------------------
# ExactMatchScorer — pure synchronous scorer (< 1ms per call, no LLM)
# ---------------------------------------------------------------------------

class ExactMatchScorer:
    """Scores agent answers against ground truth using rule-based comparison.

    Q1=B: Numeric comparison uses 1% relative tolerance.
    Q2=A: String comparison uses strip + lower only.
    """

    @staticmethod
    def score(actual_str: str, expected: Any) -> bool:
        """Return True if actual_str matches expected within defined tolerance."""
        if isinstance(expected, bool):
            # bool is a subclass of int — compare as string
            return actual_str.strip().lower() == str(expected).lower()

        if isinstance(expected, (int, float)):
            try:
                actual_num = float(actual_str.strip())
            except (ValueError, TypeError):
                return False
            expected_f = float(expected)
            denom = max(abs(expected_f), 1.0)  # prevents div-by-zero when expected==0
            return abs(actual_num - expected_f) / denom <= 0.01  # Q1=B: 1% relative

        if isinstance(expected, str):
            return actual_str.strip().lower() == expected.strip().lower()  # Q2=A

        if isinstance(expected, list):
            try:
                actual_list = json.loads(actual_str)
                if not isinstance(actual_list, list):
                    return False
            except (json.JSONDecodeError, ValueError, TypeError):
                return False
            if len(actual_list) != len(expected):
                return False
            return all(
                ExactMatchScorer.score(str(a), e)
                for a, e in zip(actual_list, expected)
            )

        # fallback: stringify both
        return str(actual_str).strip() == str(expected).strip()


# ---------------------------------------------------------------------------
# LLMJudgeScorer — async LLM-as-judge scorer (Q10=A: single JSON response)
# ---------------------------------------------------------------------------

class LLMJudgeScorer:
    """Calls the LLM to judge correctness when ExactMatch fails.

    BR-U4-18: Uses settings.OPENROUTER_MODEL; separate client instance.
    BR-U4-19: Parse failure returns JudgeVerdict(passed=False, ...).
    BR-U4-20: response_format={"type": "json_object"} enforces structured output.
    """

    @staticmethod
    async def score(
        question: str,
        actual: str,
        expected: Any,
        client: openai.AsyncOpenAI,
    ) -> JudgeVerdict:
        """Return JudgeVerdict from LLM judge. Never raises (BR-U4-19)."""
        user_content = (
            f"Question: {question}\n"
            f"Expected: {expected}\n"
            f"Agent answered: {actual}\n"
            "Is the agent's answer correct?"
        )
        try:
            response = await client.chat.completions.create(
                model=settings.openrouter_model,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
            return JudgeVerdict(
                passed=bool(data["passed"]),
                rationale=str(data.get("rationale", "")),
                confidence=float(data.get("confidence", 0.0)),
            )
        except Exception:
            # BR-U4-19: parse error → conservative failure, never propagate
            return JudgeVerdict(passed=False, rationale="judge_parse_error", confidence=0.0)


# ---------------------------------------------------------------------------
# QueryTraceRecorder — write-once trace file writer (SEC-U4-04)
# ---------------------------------------------------------------------------

class QueryTraceRecorder:
    """Writes one TrialRecord to a JSON file under results/traces/{run_id}/."""

    @staticmethod
    def write(trial: TrialRecord, run_id: str, results_dir: Path) -> None:
        """Write trial to disk. Raises ValueError if path already exists (BR-U4-12)."""
        path = (
            results_dir / "traces" / run_id
            / f"{trial.query_id}_trial_{trial.trial_index}.json"
        )
        if path.exists():
            raise ValueError(f"Trace already exists (duplicate trial): {path}")  # SEC-U4-04
        path.parent.mkdir(parents=True, exist_ok=True)  # BR-U4-13
        path.write_text(json.dumps(trial.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# ScoreLog — AppendOnlyScoreWriter (Pattern 1, SEC-U4-02)
# ---------------------------------------------------------------------------

class ScoreLog:
    """Append-only log of BenchmarkResult entries in results/score_log.jsonl.

    Pattern 1: AppendOnlyScoreWriter — file is NEVER opened in write/truncate mode.
    SEC-U4-02: The string "w" mode must never appear in this class's file I/O.
    """

    @staticmethod
    def append(result: BenchmarkResult, results_dir: Path) -> None:
        """Append one BenchmarkResult as a JSON line. Never truncates the file."""
        path = results_dir / "score_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(result.model_dump()) + "\n"
        with open(path, "a", encoding="utf-8") as f:  # "a" = append — never "w"
            f.write(line)

    @staticmethod
    def load_last(results_dir: Path) -> BenchmarkResult | None:
        """Return the last BenchmarkResult in the log, or None if log is empty/absent."""
        path = results_dir / "score_log.jsonl"
        if not path.exists() or path.stat().st_size == 0:
            return None
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return None
        return BenchmarkResult(**json.loads(lines[-1]))

    @staticmethod
    def load_last_before(run_id: str, results_dir: Path) -> BenchmarkResult | None:
        """Return the most recent BenchmarkResult whose run_id != run_id (the previous run)."""
        path = results_dir / "score_log.jsonl"
        if not path.exists():
            return None
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for line in reversed(lines):
            entry = BenchmarkResult(**json.loads(line))
            if entry.run_id != run_id:
                return entry
        return None


# ---------------------------------------------------------------------------
# RegressionSuite — zero-tolerance regression gate (Q6=A)
# ---------------------------------------------------------------------------

class RegressionSuite:
    """Asserts pass@1 has not dropped compared to the previous benchmark run.

    Q6=A: Zero tolerance — any drop in pass@1 is a regression.
    Q7=A: No prior run → auto-pass with previous_score=0.0.
    BR-U4-10: failed_queries lists only queries that were passing before.
    """

    @staticmethod
    def check(current: BenchmarkResult, results_dir: Path) -> RegressionResult:
        """Compare current run against previous run; return RegressionResult."""
        previous = ScoreLog.load_last_before(current.run_id, results_dir)

        if previous is None:  # Q7=A: no baseline — first run auto-passes
            return RegressionResult(
                passed=True,
                current_score=current.pass_at_1,
                previous_score=0.0,
                delta=current.pass_at_1,
                failed_queries=[],
            )

        delta = current.pass_at_1 - previous.pass_at_1

        # BR-U4-10: queries that were passing before but are failing now
        previously_passed = {
            qid for qid, score in previous.per_query_scores.items() if score >= 1.0
        }
        currently_failed = {
            qid for qid, score in current.per_query_scores.items() if score < 1.0
        }
        failed_queries = sorted(previously_passed & currently_failed)

        passed = current.pass_at_1 >= previous.pass_at_1  # Q6=A: strict, zero tolerance

        return RegressionResult(
            passed=passed,
            current_score=current.pass_at_1,
            previous_score=previous.pass_at_1,
            delta=delta,
            failed_queries=failed_queries,
        )


# ---------------------------------------------------------------------------
# BenchmarkRunner — Patterns 2, 3, 4
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """Runs N trials for a single DABQuery against the live agent.

    Pattern 2: SemaphoreThrottledCaller — max _AGENT_CONCURRENCY concurrent calls.
    Pattern 3: FailSafeTrialRunner — HTTP errors recorded as passed=False.
    Pattern 4: WaterfallScorer — ExactMatch first; LLMJudge only on failure.
    """

    async def run_query(
        self,
        query: DABQuery,
        n_trials: int,
        run_id: str,
        results_dir: Path,
        session: aiohttp.ClientSession,
        sem: asyncio.Semaphore,
        llm_client: openai.AsyncOpenAI,
        agent_url: str,
    ) -> float:
        """Run n_trials for query; return pass@1 (first trial result only, Q5=A)."""
        tasks = [
            self._run_trial_guarded(sem, session, query, i, agent_url, run_id, results_dir, llm_client)
            for i in range(n_trials)
        ]
        trials: list[TrialRecord] = await asyncio.gather(*tasks)
        return 1.0 if trials[0].passed else 0.0  # Q5=A: pass@1 = first trial only

    async def _run_trial_guarded(
        self,
        sem: asyncio.Semaphore,
        session: aiohttp.ClientSession,
        query: DABQuery,
        trial_index: int,
        agent_url: str,
        run_id: str,
        results_dir: Path,
        llm_client: openai.AsyncOpenAI,
    ) -> TrialRecord:
        async with sem:  # Pattern 2: blocks until slot available
            return await self._run_trial(
                session, query, trial_index, agent_url, run_id, results_dir, llm_client
            )

    async def _run_trial(
        self,
        session: aiohttp.ClientSession,
        query: DABQuery,
        trial_index: int,
        agent_url: str,
        run_id: str,
        results_dir: Path,
        llm_client: openai.AsyncOpenAI,
    ) -> TrialRecord:
        start = time.monotonic()
        trial: TrialRecord
        try:
            async with session.post(
                f"{agent_url}/query",
                json={"question": query.question},
                timeout=aiohttp.ClientTimeout(total=60),  # BR-U4-22: 60s timeout
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            elapsed_ms = (time.monotonic() - start) * 1000.0

            trial = TrialRecord(
                query_id=query.id,
                trial_index=trial_index,
                question=query.question,
                agent_answer=str(data.get("answer", "")),
                agent_confidence=float(data.get("confidence", 0.0)),
                session_id=str(data.get("session_id", "")),
                elapsed_ms=elapsed_ms,
            )
            trial = await self._score_trial(trial, query.expected_answer, llm_client)

        except (aiohttp.ClientError, asyncio.TimeoutError):
            # Pattern 3: FailSafeTrialRunner — absorb error, run continues (BR-U4-21)
            elapsed_ms = (time.monotonic() - start) * 1000.0
            logger.warning(
                "trial_http_error query_id=%s trial_index=%d",
                query.id,
                trial_index,
            )  # SEC-U4-01: query_id only — no question text in log
            trial = TrialRecord(
                query_id=query.id,
                trial_index=trial_index,
                question=query.question,
                agent_answer="http_error",
                agent_confidence=0.0,
                session_id="",
                elapsed_ms=elapsed_ms,
                exact_match_passed=False,
                passed=False,
            )

        QueryTraceRecorder.write(trial, run_id, results_dir)
        logger.debug(
            "trial_complete query_id=%s trial_index=%d passed=%s elapsed_ms=%.1f scorer=%s",
            trial.query_id,
            trial.trial_index,
            trial.passed,
            trial.elapsed_ms,
            "llm_judge" if trial.judge_verdict is not None else "exact_match",
        )  # SEC-U4-01: no question/answer content
        return trial

    async def _score_trial(
        self,
        trial: TrialRecord,
        expected: Any,
        llm_client: openai.AsyncOpenAI,
    ) -> TrialRecord:
        """Pattern 4: WaterfallScorer — ExactMatch first; LLMJudge only on failure."""
        exact = ExactMatchScorer.score(trial.agent_answer, expected)
        trial.exact_match_passed = exact
        if exact:
            trial.passed = True
            return trial  # early exit — LLMJudge never called (BR-U4-04)

        # Waterfall stage 2: LLM judge (BR-U4-04/05)
        verdict = await LLMJudgeScorer.score(
            trial.question, trial.agent_answer, expected, llm_client
        )
        trial.judge_verdict = verdict
        trial.passed = verdict.passed
        return trial


# ---------------------------------------------------------------------------
# EvaluationHarness — public orchestrator
# ---------------------------------------------------------------------------

class EvaluationHarness:
    """Orchestrates a full benchmark run against the agent.

    Usage:
        harness = EvaluationHarness()
        result, regression = await harness.run(queries, agent_url, n_trials=1)
    """

    async def run(
        self,
        queries: list[DABQuery],
        agent_url: str,
        n_trials: int = 1,
        results_dir: Path = Path("results"),
    ) -> tuple[BenchmarkResult, RegressionResult]:
        """Run benchmark; return (BenchmarkResult, RegressionResult).

        Always appends to score_log.jsonl. Always returns even on partial failures.
        """
        run_id = str(uuid.uuid4())
        logger.info(
            "benchmark_start run_id=%s agent_url=%s n_trials=%d total_queries=%d",
            run_id,
            agent_url,
            n_trials,
            len(queries),
        )  # SEC-U4-01: metadata only

        scores: dict[str, float] = {}
        runner = BenchmarkRunner()
        sem = asyncio.Semaphore(_AGENT_CONCURRENCY)  # Pattern 2: shared across all tasks
        llm_client = openai.AsyncOpenAI(
            api_key=settings.openrouter_api_key,  # SEC-U4-03: from env only
            base_url=settings.openrouter_base_url,
        )

        async with aiohttp.ClientSession() as session:
            for query in queries:
                score = await runner.run_query(
                    query, n_trials, run_id, results_dir,
                    session, sem, llm_client, agent_url,
                )
                scores[query.id] = score

        pass_at_1 = sum(scores.values()) / len(scores) if scores else 0.0

        result = BenchmarkResult(
            run_id=run_id,
            timestamp=time.time(),
            agent_url=agent_url,
            n_trials=n_trials,
            total_queries=len(queries),
            pass_at_1=pass_at_1,
            per_query_scores=scores,
        )
        ScoreLog.append(result, results_dir)  # Pattern 1: append-only
        regression = RegressionSuite.check(result, results_dir)

        logger.info(
            "benchmark_complete run_id=%s pass_at_1=%.4f regression_passed=%s delta=%.4f",
            run_id,
            pass_at_1,
            regression.passed,
            regression.delta,
        )  # SEC-U4-01: metadata only
        return result, regression
