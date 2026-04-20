"""Public facade for the OracleForge Data Agent.

FR-01: run_agent(question, db_hints) -> AgentResult is the single public entry point.
FR-08: AGENT.md is loaded into Layer 3 at session start via OracleForgeConductor.
BR-U4-01: This module is intentionally thin — all orchestration logic lives in conductor.py.
SEC-03: Structured logging.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from agent.data_agent.config import AGENT_SESSION_ID
from agent.data_agent.types import AgentResult
from agent.runtime.conductor import OracleForgeConductor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OracleForgeAgent class
# ---------------------------------------------------------------------------


class OracleForgeAgent:
    """Thin wrapper over OracleForgeConductor.

    Provides a stable public API for the agent.  All orchestration logic
    (context assembly, LLM calls, tool invocations, self-correction, memory,
    event emission) is delegated to ``OracleForgeConductor``.
    """

    def __init__(self, session_id: Optional[str] = None) -> None:
        """Initialise the agent for a new or resumed session.

        Parameters
        ----------
        session_id:
            Optional identifier for session continuity.  Defaults to the
            value of ``AGENT_SESSION_ID`` env var, or a fresh UUID.
        """
        resolved_session = session_id or AGENT_SESSION_ID
        logger.info("OracleForgeAgent init: session_id=%s", resolved_session)
        self._conductor = OracleForgeConductor(session_id=resolved_session)

    def run_agent(
        self,
        question: str,
        db_hints: list[str],
        dataset_context: Optional[dict] = None,
    ) -> AgentResult:
        """Run the agent pipeline and return a structured result.

        Parameters
        ----------
        question:
            The user's analytics question (max 4096 characters).
        db_hints:
            Database type hints (e.g. ``["postgres", "duckdb"]``).
            Max 10 items.
        dataset_context:
            Optional extra context describing the active dataset. Keys:
            ``dataset`` (str), ``db_description`` (str), ``hints`` (str),
            ``available_databases`` (list of {type, name} descriptors).
            Not used for routing decisions — only to inform the LLM
            about available tables and join keys.
        """
        logger.info(
            "OracleForgeAgent.run_agent: question=%.80s db_hints=%s dataset=%s",
            question,
            db_hints,
            (dataset_context or {}).get("dataset", ""),
        )
        return self._conductor.run(question, db_hints, dataset_context)


# ---------------------------------------------------------------------------
# Module-level convenience function (FR-01)
# ---------------------------------------------------------------------------


def run_agent(
    question: str,
    db_hints: list[str],
    dataset_context: Optional[dict] = None,
) -> AgentResult:
    """Module-level convenience wrapper around ``OracleForgeAgent``.

    Creates a fresh agent instance for each call.  For session continuity
    across multiple queries, use the ``OracleForgeAgent`` class directly.

    Each invocation is given a freshly-generated ``session_id`` so that
    interaction memory from one question cannot leak into the next —
    critical for batch/eval scenarios where many unrelated questions run
    back-to-back in the same Python process.

    Parameters
    ----------
    question:
        The user's analytics question (max 4096 characters).
    db_hints:
        Database type hints (e.g. ``["postgres", "duckdb"]``).
    dataset_context:
        Optional dataset-level context (schema, hints, available DBs).
    """
    agent = OracleForgeAgent(session_id=str(uuid.uuid4()))
    return agent.run_agent(question, db_hints, dataset_context)
