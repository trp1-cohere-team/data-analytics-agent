"""Multi-step execution plan builder for the OracleForge Data Agent.

FR-04: Generates ordered ExecutionStep lists from a question + context.
FR-04: Produces correction proposals when a step fails.
SEC-03: Structured logging throughout.
SEC-15: All external calls have explicit error handling.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import requests

from agent.data_agent.config import (
    AGENT_MAX_EXECUTION_STEPS,
    AGENT_MAX_TOKENS,
    AGENT_OFFLINE_MODE,
    AGENT_TEMPERATURE,
    AGENT_TIMEOUT_SECONDS,
    OFFLINE_LLM_RESPONSE,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from agent.data_agent.types import (
    ContextPacket,
    ExecutionStep,
    FailureDiagnosis,
    ToolDescriptor,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_plan(
    question: str,
    context: ContextPacket,
    tools: list[ToolDescriptor],
) -> list[ExecutionStep]:
    """Build a multi-step execution plan for *question*.

    Parameters
    ----------
    question:
        The user's analytics question.
    context:
        Assembled 6-layer context packet.
    tools:
        Available tool descriptors from the MCP registry.

    Returns
    -------
    list[ExecutionStep]
        Ordered plan steps, capped at ``AGENT_MAX_EXECUTION_STEPS``.
    """
    if AGENT_OFFLINE_MODE:
        first_tool = tools[0].name if tools else "query_postgresql"
        logger.debug("build_plan: offline stub — single-step plan for tool '%s'", first_tool)
        return [
            ExecutionStep(
                step_number=1,
                action="query",
                tool_name=first_tool,
                parameters={},
                expected_outcome="Return query results from the database.",
                status="pending",
            )
        ]

    tool_lines = "\n".join(f"  - {t.name} ({t.kind}): {t.description}" for t in tools)
    context_summary = _summarise_context(context)

    prompt = (
        "You are a data analytics agent. Given the question and available tools, "
        "produce a JSON execution plan as a list of steps.\n\n"
        f"Question: {question}\n\n"
        f"Context summary:\n{context_summary}\n\n"
        f"Available tools:\n{tool_lines}\n\n"
        "Respond ONLY with a JSON array of step objects. Each step must have:\n"
        '  {"step_number": int, "action": str, "tool_name": str, '
        '"parameters": {}, "expected_outcome": str}\n'
        f"Limit to {AGENT_MAX_EXECUTION_STEPS} steps."
    )

    response = _call_llm(prompt)
    steps = _parse_plan(response)

    if not steps:
        first_tool = tools[0].name if tools else "query_postgresql"
        logger.warning("build_plan: LLM returned no parseable steps; using single-step fallback")
        return [
            ExecutionStep(
                step_number=1,
                action="query",
                tool_name=first_tool,
                parameters={},
                expected_outcome="Return query results from the database.",
                status="pending",
            )
        ]

    # Cap at max steps
    steps = steps[: AGENT_MAX_EXECUTION_STEPS]
    logger.info("build_plan: generated %d step(s) for question: %.80s", len(steps), question)
    return steps


def propose_correction(diagnosis: FailureDiagnosis, context: ContextPacket) -> str:
    """Propose a correction string for a failed execution step.

    Parameters
    ----------
    diagnosis:
        Failure classification from ``failure_diagnostics.classify()``.
    context:
        Current 6-layer context packet (used for context summary in message).

    Returns
    -------
    str
        Human-readable correction suggestion.
    """
    category_hints: dict[str, str] = {
        "query": (
            "The query contains a syntax error. "
            "Fix the SQL/aggregation syntax and ensure column names match the schema."
        ),
        "join-key": (
            "A join key is missing or mismatched. "
            "Inspect the schema to identify the correct foreign-key columns."
        ),
        "db-type": (
            "The wrong database tool was selected. "
            "Switch to a different tool that matches the required database type."
        ),
        "data-quality": (
            "The data quality is insufficient to answer the question. "
            "Verify that the required data exists and is correctly formatted."
        ),
    }

    base_hint = category_hints.get(
        diagnosis.category,
        "Review the error and adjust the tool call parameters.",
    )

    parts = [base_hint]
    if diagnosis.suggested_fix:
        parts.append(f"Suggested fix: {diagnosis.suggested_fix}")
    if diagnosis.original_error:
        parts.append(f"Original error summary: {diagnosis.original_error[:200]}")

    correction = " ".join(parts)
    logger.debug("propose_correction: category=%s", diagnosis.category)
    return correction


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _summarise_context(context: ContextPacket) -> str:
    """Return a compact text summary of the context packet."""
    parts: list[str] = []
    if context.table_usage:
        parts.append(f"Schema/Tools:\n{context.table_usage[:300]}")
    if context.institutional_knowledge:
        parts.append(f"Institutional knowledge:\n{context.institutional_knowledge[:200]}")
    if context.interaction_memory:
        parts.append(f"Memory:\n{context.interaction_memory[:200]}")
    return "\n\n".join(parts) if parts else "(no context)"


def _call_llm(prompt: str) -> dict:
    """Call OpenRouter LLM and return the raw response dict.

    SEC-15: All network errors are caught and a safe stub is returned.
    """
    try:
        resp = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": OPENROUTER_APP_NAME,
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": AGENT_MAX_TOKENS,
                "temperature": AGENT_TEMPERATURE,
            },
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        logger.warning("execution_planner: LLM call timed out")
        return OFFLINE_LLM_RESPONSE
    except requests.RequestException as exc:
        logger.warning("execution_planner: LLM call failed: %s", exc)
        return OFFLINE_LLM_RESPONSE


def _extract_content(response: dict) -> str:
    """Extract text content from an LLM response dict."""
    try:
        choices = response.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
    except (IndexError, AttributeError, TypeError):
        pass
    return ""


def _parse_plan(response: dict) -> list[ExecutionStep]:
    """Parse LLM response into a list of ExecutionStep objects.

    SEC-13: Untrusted JSON is validated before use — unknown keys are ignored,
    values are type-checked before constructing ExecutionStep.
    """
    content = _extract_content(response)
    if not content:
        return []

    # Strip markdown code fences if present
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped

    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError:
        # Try to find the JSON array within the content
        start = stripped.find("[")
        end = stripped.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                raw = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                logger.debug("_parse_plan: could not parse LLM output as JSON")
                return []
        else:
            logger.debug("_parse_plan: no JSON array found in LLM output")
            return []

    if not isinstance(raw, list):
        logger.debug("_parse_plan: expected list, got %s", type(raw).__name__)
        return []

    steps: list[ExecutionStep] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            step = ExecutionStep(
                step_number=int(item.get("step_number", idx + 1)),
                action=str(item.get("action", "query")),
                tool_name=str(item.get("tool_name", "")),
                parameters=item.get("parameters", {}) if isinstance(item.get("parameters"), dict) else {},
                expected_outcome=str(item.get("expected_outcome", "")),
                status="pending",
            )
            steps.append(step)
        except (ValueError, TypeError) as exc:
            logger.debug("_parse_plan: skipping malformed step %d: %s", idx, exc)

    return steps
