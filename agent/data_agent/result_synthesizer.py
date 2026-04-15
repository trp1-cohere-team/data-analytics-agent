"""Answer synthesizer for the OracleForge Data Agent.

FR-01: Synthesizes a grounded answer from execution evidence + context.
FR-01: Computes a confidence score.
SEC-03: Structured logging throughout.
SEC-15: All external calls have explicit error handling.
"""

from __future__ import annotations

import logging

import requests

from agent.data_agent.config import (
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
from agent.data_agent.types import ContextPacket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def synthesize_answer(
    question: str,
    evidence: list[dict],
    context: ContextPacket,
) -> tuple[str, float]:
    """Synthesize a grounded answer from execution evidence.

    Parameters
    ----------
    question:
        The original user question.
    evidence:
        List of execution result dicts.  Each dict may have keys:
        ``success`` (bool), ``result`` (str), ``error`` (str),
        ``corrected`` (bool), ``tool`` (str).
    context:
        Assembled 6-layer context packet (used for synthesis prompt).

    Returns
    -------
    tuple[str, float]
        ``(answer_text, confidence)`` where confidence is in [0.0, 1.0].
    """
    successful = [e for e in evidence if e.get("success")]

    if not successful:
        logger.info("synthesize_answer: no successful evidence — returning fallback")
        return ("Unable to determine the answer from the available data.", 0.1)

    if AGENT_OFFLINE_MODE:
        logger.debug("synthesize_answer: offline mode — returning stub answer")
        stub_content = (
            OFFLINE_LLM_RESPONSE.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "OFFLINE_STUB: deterministic stub response.")
        )
        confidence = _compute_confidence(evidence)
        return (stub_content, confidence)

    # Build synthesis prompt
    results_text = "\n".join(
        f"- Tool {e.get('tool', 'unknown')}: {str(e.get('result', ''))[:300]}"
        for e in successful
    )
    context_summary = _summarise_context(context)

    synthesis_prompt = (
        "You are a data analytics assistant. Using the query results below, "
        "provide a concise, grounded answer to the question. "
        "Do not speculate — only use the data provided.\n\n"
        f"Question: {question}\n\n"
        f"Context:\n{context_summary}\n\n"
        f"Query results:\n{results_text}\n\n"
        "Provide a clear, factual answer."
    )

    response = _call_llm(synthesis_prompt)
    answer_text = _extract_content(response)

    if not answer_text:
        logger.warning("synthesize_answer: LLM returned empty content — using fallback")
        answer_text = "Unable to determine the answer from the available data."

    confidence = _compute_confidence(evidence)
    logger.info(
        "synthesize_answer: confidence=%.2f successful=%d total=%d",
        confidence,
        len(successful),
        len(evidence),
    )
    return (answer_text, confidence)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_confidence(evidence: list[dict]) -> float:
    """Compute a confidence score from execution evidence.

    Formula:
        base       = successful_steps / total_steps
        penalty    = corrections * 0.1
        confidence = clamp(base - penalty, 0.0, 1.0)
    """
    total = len(evidence)
    if total == 0:
        return 0.1

    successes = sum(1 for e in evidence if e.get("success"))
    corrections = sum(1 for e in evidence if e.get("corrected"))

    base = successes / total
    penalty = corrections * 0.1
    return max(0.0, min(1.0, base - penalty))


def _summarise_context(context: ContextPacket) -> str:
    """Return a compact text summary of the context packet."""
    parts: list[str] = []
    if context.table_usage:
        parts.append(f"Schema/Tools:\n{context.table_usage[:300]}")
    if context.institutional_knowledge:
        parts.append(f"Knowledge:\n{context.institutional_knowledge[:200]}")
    return "\n\n".join(parts) if parts else "(no context)"


def _call_llm(prompt: str) -> dict:
    """Call OpenRouter LLM and return the raw response dict.

    SEC-15: All network errors are caught; offline stub is returned on failure.
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
        logger.warning("result_synthesizer: LLM call timed out")
        return OFFLINE_LLM_RESPONSE
    except requests.RequestException as exc:
        logger.warning("result_synthesizer: LLM call failed: %s", exc)
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
