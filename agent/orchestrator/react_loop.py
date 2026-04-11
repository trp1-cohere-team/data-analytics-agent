"""Orchestrator — ReAct loop implementation.

Design decisions:
  - Q1=B: LLM returns JSON {"reasoning", "action", "action_input", "confidence"} — no function calling
  - Q2=C: max_iterations hit → "could not answer" response with confidence=0.0
  - Q3=A: LLM-reported confidence float in each Thought
  - Q4=B: query_database action_input is full QueryPlan JSON
  - Q5=B: CorrectionEngine called on failure; loops back to think() with error observation
  - Pattern 1: ExponentialBackoffRetry on RateLimitError (max 3 attempts)
  - Pattern 2: PromptCacheBuilder — static prompt cached; dynamic parts rebuilt per think()
  - Pattern 6: DependencyInjectedLLMClient
  - SEC-U1-01: think/act logs contain only metadata — never reasoning text or observation content
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import openai

from agent.config import settings
from agent.models import (
    ContextBundle,
    CorrectionEntry,
    ExecutionFailure,
    Observation,
    OrchestratorResult,
    QueryPlan,
    ReactState,
    Thought,
    TraceStep,
)

_logger = logging.getLogger("agent.orchestrator")

_FALLBACK_THOUGHT = Thought(
    reasoning="LLM response parse error",
    chosen_action="FINAL_ANSWER",
    action_input={"answer": "I encountered an error processing your request."},
    confidence=0.0,
)

_COULD_NOT_ANSWER = "I could not answer this question within the iteration limit."

# ---------------------------------------------------------------------------
# Structured log helpers (SEC-U1-01)
# ---------------------------------------------------------------------------

def _log_think_step(session_id: str, iteration: int, action: str) -> None:
    _logger.debug("think_step", extra={
        "session_id": session_id, "iteration": iteration, "action": action,
    })


def _log_act_step(session_id: str, iteration: int, success: bool, elapsed_ms: float) -> None:
    _logger.debug("act_step", extra={
        "session_id": session_id, "iteration": iteration,
        "success": success, "elapsed_ms": round(elapsed_ms, 1),
    })


def _log_run_complete(session_id: str, iterations: int, confidence: float) -> None:
    _logger.info("run_complete", extra={
        "session_id": session_id, "iterations": iterations,
        "confidence": round(confidence, 4),
    })

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """ReAct loop agent — think → act → observe until FINAL_ANSWER or iteration limit."""

    def __init__(
        self,
        llm_client: openai.AsyncOpenAI,
        engine: Any,           # MultiDBEngine
        kb: Any,               # KnowledgeBase
        memory: Any,           # MemoryManager
        retriever: Any,        # MultiPassRetriever
        correction_engine: Any,  # CorrectionEngine
        max_correction_attempts: int | None = None,
    ) -> None:
        self._llm = llm_client
        self._engine = engine
        self._kb = kb
        self._memory = memory
        self._retriever = retriever
        self._correction_engine = correction_engine
        self._max_correction_attempts = (
            max_correction_attempts or settings.max_correction_attempts
        )
        # PromptCacheBuilder — Pattern 2
        self._static_prompt: str | None = None
        self._static_prompt_layer2_hash: int = 0

    # ------------------------------------------------------------------
    # Public: run()
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        session_id: str,
        context: ContextBundle,
        max_iterations: int | None = None,
        confidence_threshold: float | None = None,
    ) -> OrchestratorResult:
        """Execute the ReAct loop and return final result (BR-U1-03, BR-U1-04)."""
        max_iter = max_iterations or settings.max_react_iterations
        threshold = confidence_threshold or settings.confidence_threshold

        state = ReactState(query=query, session_id=session_id)

        while not state.terminated and state.iteration < max_iter:
            t0 = time.monotonic()
            state.iteration += 1

            thought = await self.think(state, context)
            _log_think_step(session_id, state.iteration, thought.chosen_action)

            observation = await self.act(thought, context)
            elapsed = (time.monotonic() - t0) * 1000
            _log_act_step(session_id, state.iteration, observation.success, elapsed)

            state = self.observe(observation, state)

            # Record trace step
            state.history.append(TraceStep(
                iteration=state.iteration,
                thought=thought.reasoning[:500],  # truncate for storage — not logged
                action=thought.chosen_action,
                action_input=thought.action_input,
                observation=str(observation.result)[:500] if observation.success else str(observation.error)[:500],
                timestamp=time.time(),
            ))

            if thought.chosen_action == "FINAL_ANSWER":
                state.terminated = True
                state.final_answer = thought.action_input.get("answer")
                state.confidence = thought.confidence
                if state.confidence >= threshold:
                    break

        # BR-U1-03: max_iterations reached without FINAL_ANSWER (Q2=C)
        if not state.terminated:
            _log_run_complete(session_id, max_iter, 0.0)
            return OrchestratorResult(
                answer=_COULD_NOT_ANSWER,
                query_trace=state.history,
                confidence=0.0,
                session_id=session_id,
                iterations_used=max_iter,
            )

        _log_run_complete(session_id, state.iteration, state.confidence)
        return OrchestratorResult(
            answer=state.final_answer,
            query_trace=state.history,
            confidence=state.confidence,
            session_id=session_id,
            iterations_used=state.iteration,
        )

    # ------------------------------------------------------------------
    # think()
    # ------------------------------------------------------------------

    async def think(self, state: ReactState, context: ContextBundle) -> Thought:
        """LLM call → JSON parse → Thought (Q1=B, Q3=A)."""
        messages = self._build_messages(state, context)
        try:
            raw = await self._call_llm(messages)
            content = raw.content or ""
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed = json.loads(content.strip())
            return Thought(
                reasoning=parsed.get("reasoning", ""),
                chosen_action=parsed.get("action", "FINAL_ANSWER"),
                action_input=parsed.get("action_input", {}),
                confidence=float(parsed.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            _logger.warning("think_parse_error", extra={"session_id": state.session_id})
            return _FALLBACK_THOUGHT

    # ------------------------------------------------------------------
    # act()
    # ------------------------------------------------------------------

    async def act(self, thought: Thought, context: ContextBundle) -> Observation:
        """Dispatch to the tool specified by thought.chosen_action."""
        action = thought.chosen_action
        inp = thought.action_input

        if action == "query_database":
            return await self._act_query_database(inp, context)
        if action == "search_kb":
            return await self._act_search_kb(inp, context)
        if action == "extract_from_text":
            return await self._act_extract_from_text(inp)
        if action == "resolve_join_keys":
            return await self._act_resolve_join_keys(inp)
        if action == "FINAL_ANSWER":
            return Observation(action="FINAL_ANSWER", result=inp.get("answer"), success=True)

        # Unknown action — treat as no-op
        return Observation(
            action=action, result=None, success=False,
            error=f"Unknown action: {action!r}",
        )

    async def _act_query_database(self, inp: dict, context: ContextBundle) -> Observation:
        try:
            plan = QueryPlan(**inp)  # Q4=B: LLM provides full QueryPlan
        except Exception as exc:
            return Observation(action="query_database", result=None, success=False, error=str(exc))

        result = await self._engine.execute_plan(plan)

        if result.failures:
            # Q5=B: call CorrectionEngine; loop back to think() with error observation
            failure = result.failures[0]
            correction = await self._handle_correction(failure, plan, context)
            if correction and correction.corrected_plan:
                result = await self._engine.execute_plan(correction.corrected_plan)

        if result.failures and not result.merged_rows:
            return Observation(
                action="query_database", result=None, success=False,
                error=result.failures[0].error_message,
            )
        return Observation(action="query_database", result=result.merged_rows, success=True)

    async def _act_search_kb(self, inp: dict, context: ContextBundle) -> Observation:
        query = inp.get("query", "")
        docs = await self._kb.load_documents("domain")
        relevant = self._retriever.retrieve(query, docs) if docs else []
        return Observation(action="search_kb", result=relevant, success=True)

    async def _act_extract_from_text(self, inp: dict) -> Observation:
        text = inp.get("text", "")
        question = inp.get("question", "")
        prompt = [
            {"role": "user", "content": f"Extract from the following text:\n\n{text}\n\nQuestion: {question}"}
        ]
        try:
            raw = await self._call_llm(prompt)
            return Observation(action="extract_from_text", result=raw.content, success=True)
        except Exception as exc:
            return Observation(action="extract_from_text", result=None, success=False, error=str(exc))

    async def _act_resolve_join_keys(self, inp: dict) -> Observation:
        try:
            from agent.execution.engine import _JoinKeyResolver
            plan = QueryPlan(**inp.get("plan", inp))
            resolver = _JoinKeyResolver()
            resolved = resolver.pre_execute_resolve(plan)
            return Observation(action="resolve_join_keys", result=resolved.model_dump(), success=True)
        except Exception as exc:
            return Observation(action="resolve_join_keys", result=None, success=False, error=str(exc))

    # ------------------------------------------------------------------
    # observe()
    # ------------------------------------------------------------------

    def observe(self, observation: Observation, state: ReactState) -> ReactState:
        """Update ReactState based on observation. Termination handled in run()."""
        # State is immutable-like; return updated copy via model_copy
        return state.model_copy(update={
            "final_answer": observation.result if observation.action == "FINAL_ANSWER" else state.final_answer,
        })

    # ------------------------------------------------------------------
    # _handle_correction() — Q5=B
    # ------------------------------------------------------------------

    async def _handle_correction(
        self, failure: ExecutionFailure, plan: QueryPlan, context: ContextBundle
    ) -> Any | None:
        """Call CorrectionEngine; append correction to KB regardless of outcome."""
        import uuid as _uuid
        original_query = plan.sub_queries[0].query if plan.sub_queries else ""
        try:
            correction = await self._correction_engine.correct(
                failure=failure,
                original_query=original_query,
                context=context,
            )
            entry = CorrectionEntry(
                id=str(_uuid.uuid4()),
                timestamp=time.time(),
                session_id="orchestrator",
                failure_type=failure.error_type.upper(),
                original_query=original_query,
                corrected_query=correction.corrected_query,
                error_message=failure.error_message,
                fix_strategy=correction.fix_strategy,
                attempt_number=correction.attempt_number,
                success=correction.success,
            )
            await self._kb.append_correction(entry)
            return correction
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # _call_llm() — Pattern 1: ExponentialBackoffRetry
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[dict], _attempt: int = 0) -> Any:
        """OpenRouter LLM call with exponential backoff on RateLimitError only."""
        try:
            response = await self._llm.chat.completions.create(
                model=settings.openrouter_model,
                messages=messages,
            )
            return response.choices[0].message
        except openai.RateLimitError:
            if _attempt >= 2:
                raise
            await asyncio.sleep(2 ** _attempt)
            return await self._call_llm(messages, _attempt + 1)
        # All other exceptions propagate immediately (no retry)

    # ------------------------------------------------------------------
    # _build_messages() — Pattern 2: PromptCacheBuilder
    # ------------------------------------------------------------------

    def _build_messages(self, state: ReactState, context: ContextBundle) -> list[dict]:
        """Build LLM messages: cached static prompt + dynamic corrections + history."""
        static = self._get_static_prompt(context)
        dynamic = self._format_corrections(context.corrections_ctx)
        history = self._format_history(state.history)
        return [
            {"role": "system", "content": static + "\n\n" + dynamic},
            *history,
            {"role": "user", "content": state.query},
        ]

    def _get_static_prompt(self, context: ContextBundle) -> str:
        """Lazy-build and cache static prompt (schema + domain docs + action list)."""
        layer2_hash = hash(tuple(d.path for d in context.domain_ctx.documents))
        if self._static_prompt is None or self._static_prompt_layer2_hash != layer2_hash:
            self._static_prompt = self._build_static_prompt(context)
            self._static_prompt_layer2_hash = layer2_hash
        return self._static_prompt

    def _build_static_prompt(self, context: ContextBundle) -> str:
        schema_text = self._format_schema(context.schema_ctx)
        docs_text = self._format_domain_docs(context.domain_ctx)
        return (
            "You are a data analytics agent. You have access to multiple databases "
            "and a knowledge base.\n\n"
            "Available actions (respond with valid JSON only):\n"
            "- query_database: action_input = full QueryPlan JSON object\n"
            "- search_kb: action_input = {\"query\": \"<search terms>\"}\n"
            "- extract_from_text: action_input = {\"text\": \"...\", \"question\": \"...\"}\n"
            "- resolve_join_keys: action_input = {\"plan\": <QueryPlan JSON>}\n"
            "- FINAL_ANSWER: action_input = {\"answer\": <your answer>, \"confidence\": <0.0-1.0>}\n\n"
            "Always respond with ONLY valid JSON:\n"
            "{\"reasoning\": \"<your reasoning>\", \"action\": \"<action>\", "
            "\"action_input\": {...}, \"confidence\": <float 0.0-1.0>}\n\n"
            f"## Database Schemas\n{schema_text}\n\n"
            f"## Domain Knowledge\n{docs_text}"
        )

    def _format_schema(self, schema_ctx: Any) -> str:
        lines = []
        for db_name, db in schema_ctx.databases.items():
            lines.append(f"### {db_name} ({db.db_type})")
            for table in db.tables:
                cols = ", ".join(c.name for c in table.columns)
                lines.append(f"  - {table.name}: {cols}")
        return "\n".join(lines) if lines else "(no schemas loaded)"

    def _format_domain_docs(self, domain_ctx: Any) -> str:
        if not domain_ctx.documents:
            return "(no domain documents loaded)"
        return "\n\n".join(
            f"### {doc.path}\n{doc.content[:2000]}"
            for doc in domain_ctx.documents
        )

    def _format_corrections(self, corrections_ctx: Any) -> str:
        """Format Layer 3 corrections as markdown bullets (Q7=B)."""
        if not corrections_ctx.corrections:
            return ""
        lines = ["## Recent Corrections"]
        for entry in corrections_ctx.corrections[-settings.corrections_limit:]:
            snippet = entry.original_query[:80].replace("\n", " ")
            lines.append(f"- [{entry.failure_type}] `{snippet}...` → {entry.fix_strategy}")
        return "\n".join(lines)

    def _format_history(self, history: list[TraceStep]) -> list[dict]:
        """Convert TraceStep history to assistant/user message pairs."""
        messages = []
        for step in history:
            messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "reasoning": step.thought,
                    "action": step.action,
                    "action_input": step.action_input,
                    "confidence": 0.0,
                }),
            })
            messages.append({"role": "user", "content": f"Observation: {step.observation}"})
        return messages
