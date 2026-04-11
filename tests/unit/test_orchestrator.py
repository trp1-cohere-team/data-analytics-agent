"""Unit tests for agent/orchestrator/react_loop.py.

Covers:
  - run() terminates on FINAL_ANSWER
  - run() returns confidence=0.0 + "could not answer" when max_iterations reached
  - think() parses valid LLM JSON response to Thought
  - think() handles malformed JSON (graceful fallback)
  - _call_llm() retries on RateLimitError up to 3×; propagates after 3 failures
  - _call_llm() does NOT retry on non-rate-limit errors
  - _build_messages() uses cached static prompt on second call (PromptCacheBuilder)
  - PBT-U1-02: fix_syntax_error output always has len >= input len — 200 examples
"""
from __future__ import annotations

import asyncio
import json
import unittest.mock as mock
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent.correction.engine import CorrectionEngine
from agent.models import (
    ContextBundle,
    CorrectionsContext,
    DomainContext,
    OrchestratorResult,
    ReactState,
    SchemaContext,
    Thought,
)
from agent.orchestrator.react_loop import Orchestrator, _COULD_NOT_ANSWER
from tests.unit.strategies import INVARIANT_SETTINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context() -> ContextBundle:
    return ContextBundle(
        schema_ctx=SchemaContext(databases={}),
        domain_ctx=DomainContext(documents=[]),
        corrections_ctx=CorrectionsContext(corrections=[], session_memory={}),
    )


def _mock_llm_response(action: str, answer: str = "42", confidence: float = 0.9) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps({
        "reasoning": "test reasoning",
        "action": action,
        "action_input": {"answer": answer} if action == "FINAL_ANSWER" else {},
        "confidence": confidence,
    })
    return msg


def _make_orchestrator(llm_client=None) -> Orchestrator:
    llm = llm_client or MagicMock()
    engine = MagicMock()
    kb = MagicMock()
    kb.load_documents = AsyncMock(return_value=[])
    kb.append_correction = AsyncMock()
    kb.get_corrections = MagicMock(return_value=[])
    memory = MagicMock()
    memory.save_session = AsyncMock()
    retriever = MagicMock()
    retriever.retrieve = MagicMock(return_value=[])
    correction_engine = MagicMock()
    correction_engine.correct = AsyncMock(return_value=MagicMock(
        success=False, corrected_plan=None, corrected_query=None,
        fix_strategy="rule_syntax", attempt_number=1,
    ))
    return Orchestrator(
        llm_client=llm,
        engine=engine,
        kb=kb,
        memory=memory,
        retriever=retriever,
        correction_engine=correction_engine,
    )


# ---------------------------------------------------------------------------
# run() — termination paths
# ---------------------------------------------------------------------------

class TestRunTermination:
    def test_terminates_on_final_answer(self):
        llm = MagicMock()
        llm.chat = MagicMock()
        llm.chat.completions = MagicMock()
        llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=_mock_llm_response("FINAL_ANSWER", "42", 0.9))])
        )
        orch = _make_orchestrator(llm)
        ctx = _make_context()

        result = asyncio.get_event_loop().run_until_complete(
            orch.run("What is 6*7?", "sess-1", ctx, max_iterations=5, confidence_threshold=0.85)
        )
        assert result.answer == "42"
        assert result.confidence == 0.9
        assert result.iterations_used == 1

    def test_returns_could_not_answer_when_max_iterations_hit(self):
        llm = MagicMock()
        # Always returns search_kb (never FINAL_ANSWER)
        llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=_mock_llm_response("search_kb", confidence=0.3))])
        )
        orch = _make_orchestrator(llm)
        ctx = _make_context()

        result = asyncio.get_event_loop().run_until_complete(
            orch.run("test", "sess-2", ctx, max_iterations=2, confidence_threshold=0.85)
        )
        assert result.answer == _COULD_NOT_ANSWER
        assert result.confidence == 0.0
        assert result.iterations_used == 2


# ---------------------------------------------------------------------------
# think() — LLM JSON parsing
# ---------------------------------------------------------------------------

class TestThink:
    def test_parses_valid_json_to_thought(self):
        llm = MagicMock()
        msg = MagicMock()
        msg.content = json.dumps({
            "reasoning": "I need to query",
            "action": "query_database",
            "action_input": {"id": "p1", "sub_queries": [], "merge_spec": {"strategy": "UNION"}},
            "confidence": 0.7,
        })
        llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)])
        )
        orch = _make_orchestrator(llm)
        state = ReactState(query="test", session_id="s1")
        ctx = _make_context()

        thought = asyncio.get_event_loop().run_until_complete(orch.think(state, ctx))
        assert thought.chosen_action == "query_database"
        assert thought.confidence == 0.7

    def test_handles_malformed_json_with_fallback(self):
        llm = MagicMock()
        msg = MagicMock()
        msg.content = "NOT VALID JSON {{{"
        llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)])
        )
        orch = _make_orchestrator(llm)
        state = ReactState(query="test", session_id="s1")
        ctx = _make_context()

        thought = asyncio.get_event_loop().run_until_complete(orch.think(state, ctx))
        assert thought.chosen_action == "FINAL_ANSWER"
        assert thought.confidence == 0.0

    def test_handles_markdown_wrapped_json(self):
        llm = MagicMock()
        msg = MagicMock()
        msg.content = "```json\n" + json.dumps({
            "reasoning": "x",
            "action": "FINAL_ANSWER",
            "action_input": {"answer": "done"},
            "confidence": 0.95,
        }) + "\n```"
        llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)])
        )
        orch = _make_orchestrator(llm)
        state = ReactState(query="test", session_id="s1")
        ctx = _make_context()

        thought = asyncio.get_event_loop().run_until_complete(orch.think(state, ctx))
        assert thought.chosen_action == "FINAL_ANSWER"
        assert thought.confidence == 0.95


# ---------------------------------------------------------------------------
# _call_llm() — retry behavior
# ---------------------------------------------------------------------------

class TestCallLLM:
    def test_retries_rate_limit_error_up_to_3_times(self):
        llm = MagicMock()
        call_count = 0

        async def _failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise openai.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body={},
                )
            return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

        llm.chat.completions.create = _failing_then_success
        orch = _make_orchestrator(llm)

        result = asyncio.get_event_loop().run_until_complete(
            orch._call_llm([{"role": "user", "content": "test"}])
        )
        assert call_count == 3
        assert result.content == "ok"

    def test_propagates_rate_limit_after_3_failures(self):
        llm = MagicMock()

        async def _always_rate_limited(*args, **kwargs):
            raise openai.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body={},
            )

        llm.chat.completions.create = _always_rate_limited
        orch = _make_orchestrator(llm)

        with pytest.raises(openai.RateLimitError):
            asyncio.get_event_loop().run_until_complete(
                orch._call_llm([{"role": "user", "content": "test"}])
            )

    def test_does_not_retry_non_rate_limit_errors(self):
        llm = MagicMock()
        call_count = 0

        async def _connection_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise openai.APIConnectionError(request=MagicMock())

        llm.chat.completions.create = _connection_error
        orch = _make_orchestrator(llm)

        with pytest.raises(openai.APIConnectionError):
            asyncio.get_event_loop().run_until_complete(
                orch._call_llm([{"role": "user", "content": "test"}])
            )
        assert call_count == 1  # no retry


# ---------------------------------------------------------------------------
# _build_messages() — PromptCacheBuilder
# ---------------------------------------------------------------------------

class TestBuildMessages:
    def test_caches_static_prompt_on_second_call(self):
        orch = _make_orchestrator()
        ctx = _make_context()
        state = ReactState(query="test", session_id="s1")

        msgs1 = orch._build_messages(state, ctx)
        cached_prompt_id = id(orch._static_prompt)

        msgs2 = orch._build_messages(state, ctx)
        assert id(orch._static_prompt) == cached_prompt_id  # same object — not rebuilt

    def test_invalidates_cache_on_layer2_change(self):
        from agent.models import DomainContext, KBDocument
        orch = _make_orchestrator()
        ctx = _make_context()
        state = ReactState(query="test", session_id="s1")

        orch._build_messages(state, ctx)
        cached_id = id(orch._static_prompt)

        # Simulate Layer 2 document change
        new_doc = KBDocument(path="new.md", content="new content", subdirectory="domain")
        ctx2 = ctx.model_copy(update={
            "domain_ctx": DomainContext(documents=[new_doc])
        })
        orch._build_messages(state, ctx2)
        assert id(orch._static_prompt) != cached_id  # rebuilt


# ---------------------------------------------------------------------------
# PBT-U1-02: fix_syntax_error output length invariant
# ---------------------------------------------------------------------------

@given(
    query=st.text(min_size=5, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P"))),
    error=st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
)
@INVARIANT_SETTINGS["PBT-U1-02"]
def test_pbt_u1_02_fix_syntax_error_output_length(query: str, error: str):
    """PBT-U1-02: fix_syntax_error output is always >= input length (no truncation)."""
    from agent.correction.engine import CorrectionEngine
    from unittest.mock import MagicMock
    eng = CorrectionEngine(llm_client=MagicMock(), engine=MagicMock())
    result = eng.fix_syntax_error(query, error)
    assert len(result) >= len(query), (
        f"fix_syntax_error truncated output: {len(result)} < {len(query)}\n"
        f"input={query!r}\noutput={result!r}"
    )
