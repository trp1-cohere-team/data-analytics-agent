"""Unit tests for Streaming API — U7.

Tests run_stream() on the Orchestrator and the /query/stream HTTP endpoint.
All LLM and DB calls are mocked.
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from agent.models import (
    ContextBundle,
    CorrectionsContext,
    DomainContext,
    OrchestratorResult,
    QueryRequest,
    SchemaContext,
    StreamEvent,
    TraceStep,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_context() -> ContextBundle:
    return ContextBundle(
        schema_ctx=SchemaContext(),
        domain_ctx=DomainContext(),
        corrections_ctx=CorrectionsContext(),
    )


def _make_orchestrator(thoughts: list[dict]):
    """Build a minimal Orchestrator whose think() returns canned Thought objects."""
    from agent.orchestrator.react_loop import Orchestrator
    from agent.models import Thought, Observation

    orch = MagicMock(spec=Orchestrator)
    thought_objs = [
        Thought(
            reasoning=t.get("reasoning", ""),
            chosen_action=t["action"],
            action_input=t.get("action_input", {}),
            confidence=t.get("confidence", 0.9),
        )
        for t in thoughts
    ]
    observations = [
        Observation(action=t["action"], result=t.get("result"), success=True)
        for t in thoughts
    ]

    orch.think = AsyncMock(side_effect=thought_objs)
    orch.act = AsyncMock(side_effect=observations)
    orch.observe = MagicMock(side_effect=lambda obs, state: state)

    # Delegate run_stream to the real implementation
    from agent.orchestrator.react_loop import Orchestrator as RealOrch
    orch.run_stream = RealOrch.run_stream.__get__(orch)
    return orch


# ---------------------------------------------------------------------------
# StreamEvent model
# ---------------------------------------------------------------------------

def test_stream_event_to_sse_thought():
    evt = StreamEvent(type="thought", iteration=1, action="postgres_query", confidence=0.8)
    sse = evt.to_sse()
    assert sse.startswith("event: thought\n")
    assert "postgres_query" in sse
    assert sse.endswith("\n\n")


def test_stream_event_to_sse_final_answer():
    evt = StreamEvent(type="final_answer", answer="42", confidence=0.95, session_id="s1", iterations_used=2)
    sse = evt.to_sse()
    assert "event: final_answer" in sse
    payload = json.loads(sse.split("data: ")[1].strip())
    assert payload["answer"] == "42"
    assert payload["confidence"] == 0.95


def test_stream_event_exclude_none():
    """None fields must not appear in SSE output."""
    evt = StreamEvent(type="error", message="ValueError")
    sse = evt.to_sse()
    payload = json.loads(sse.split("data: ")[1].strip())
    assert "iteration" not in payload
    assert "answer" not in payload
    assert payload["message"] == "ValueError"


# ---------------------------------------------------------------------------
# Orchestrator.run_stream()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_stream_emits_thought_action_final():
    from agent.orchestrator.react_loop import Orchestrator
    from agent.models import Thought, Observation, ReactState

    orch = MagicMock()
    orch._sandbox = None
    orch._correction_engine = MagicMock()
    orch._kb = MagicMock()
    orch._retriever = MagicMock()
    orch._engine = MagicMock()
    orch._max_correction_attempts = 3
    orch._static_prompt = None
    orch._static_prompt_layer2_hash = 0

    final_thought = Thought(
        reasoning="done", chosen_action="FINAL_ANSWER",
        action_input={"answer": "Revenue is $100"}, confidence=0.95,
    )
    orch.think = AsyncMock(return_value=final_thought)
    orch.act = AsyncMock(return_value=Observation(
        action="FINAL_ANSWER", result="Revenue is $100", success=True,
    ))
    orch.observe = MagicMock(side_effect=lambda obs, state: state)

    events = []
    async for evt in Orchestrator.run_stream(
        orch,
        query="What is revenue?",
        session_id="test-1",
        context=_make_context(),
        max_iterations=10,
        confidence_threshold=0.85,
    ):
        events.append(evt)

    types = [e.type for e in events]
    assert "thought" in types
    assert "action" in types
    assert "final_answer" in types
    final = next(e for e in events if e.type == "final_answer")
    assert final.answer == "Revenue is $100"
    assert final.confidence == 0.95


@pytest.mark.asyncio
async def test_run_stream_error_emits_error_event():
    from agent.orchestrator.react_loop import Orchestrator

    orch = MagicMock()
    orch._sandbox = None
    orch._static_prompt = None
    orch._static_prompt_layer2_hash = 0
    orch.think = AsyncMock(side_effect=RuntimeError("boom"))
    orch.observe = MagicMock()

    events = []
    async for evt in Orchestrator.run_stream(
        orch,
        query="What?",
        session_id="test-err",
        context=_make_context(),
        max_iterations=10,
        confidence_threshold=0.85,
    ):
        events.append(evt)

    assert len(events) == 1
    assert events[0].type == "error"
    assert events[0].message == "RuntimeError"


@pytest.mark.asyncio
async def test_run_stream_observations_not_streamed():
    """Observation data must NOT appear as a streamed event (BR-U7-04)."""
    from agent.orchestrator.react_loop import Orchestrator
    from agent.models import Thought, Observation

    orch = MagicMock()
    orch._sandbox = None
    orch._static_prompt = None
    orch._static_prompt_layer2_hash = 0
    orch.think = AsyncMock(return_value=Thought(
        reasoning="", chosen_action="FINAL_ANSWER",
        action_input={"answer": "done"}, confidence=0.9,
    ))
    orch.act = AsyncMock(return_value=Observation(action="FINAL_ANSWER", result="done", success=True))
    orch.observe = MagicMock(side_effect=lambda obs, state: state)

    events = []
    async for evt in Orchestrator.run_stream(
        orch, query="q", session_id="s", context=_make_context(),
        max_iterations=10, confidence_threshold=0.85,
    ):
        events.append(evt)

    event_types = {e.type for e in events}
    assert "observation" not in event_types


# ---------------------------------------------------------------------------
# HTTP endpoint /query/stream
# ---------------------------------------------------------------------------

def _make_app_with_mock_orchestrator():
    """Build the FastAPI app with all internal components mocked."""
    from agent.api import app as app_module
    from agent.api.app import create_app

    mock_orch = MagicMock()
    mock_ctx_mgr = MagicMock()
    mock_mem_mgr = MagicMock()

    async def _fake_run_stream(**kwargs):
        yield StreamEvent(type="thought", iteration=1, action="FINAL_ANSWER", confidence=0.9)
        yield StreamEvent(type="action", iteration=1, tool="FINAL_ANSWER", success=True)
        yield StreamEvent(type="final_answer", answer="42", confidence=0.9, session_id="s", iterations_used=1)

    mock_orch.run_stream = _fake_run_stream
    mock_ctx_mgr.get_context_bundle = AsyncMock(return_value=_make_context())
    mock_mem_mgr.save_session = AsyncMock()

    app_module._orchestrator = mock_orch
    app_module._context_manager = mock_ctx_mgr
    app_module._memory_manager = mock_mem_mgr

    return create_app()


def test_query_stream_returns_200_text_event_stream():
    app = _make_app_with_mock_orchestrator()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/query/stream",
        json={"question": "What is the answer?"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


def test_query_stream_body_contains_sse_events():
    app = _make_app_with_mock_orchestrator()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/query/stream", json={"question": "test"})
    body = resp.text
    assert "event: thought" in body
    assert "event: final_answer" in body


def test_query_stream_final_answer_payload():
    app = _make_app_with_mock_orchestrator()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/query/stream", json={"question": "test"})
    lines = resp.text.splitlines()
    data_lines = [l for l in lines if l.startswith("data:") and "final_answer" not in l]
    final_data = next(
        (l for l in resp.text.splitlines()
         if l.startswith("data:") and "final_answer" in resp.text.split(l)[0].split("\n")[-2]),
        None,
    )
    assert "42" in resp.text


def test_existing_query_endpoint_unaffected():
    """POST /query must still work exactly as before (BR-U7-01)."""
    from agent.api import app as app_module
    from agent.api.app import create_app

    mock_orch = MagicMock()
    mock_ctx_mgr = MagicMock()
    mock_mem_mgr = MagicMock()

    mock_orch.run = AsyncMock(return_value=OrchestratorResult(
        answer="unchanged", query_trace=[], confidence=0.9,
        session_id="s", iterations_used=1,
    ))
    mock_ctx_mgr.get_context_bundle = AsyncMock(return_value=_make_context())
    mock_mem_mgr.save_session = AsyncMock()

    app_module._orchestrator = mock_orch
    app_module._context_manager = mock_ctx_mgr
    app_module._memory_manager = mock_mem_mgr

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/query", json={"question": "hello"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "unchanged"
