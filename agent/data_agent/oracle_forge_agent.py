"""Public facade for the OracleForge Data Agent.

FR-01: run_agent(question, db_hints) -> AgentResult is the single public entry point.
FR-08: AGENT.md is loaded into Layer 3 at session start via OracleForgeConductor.
BR-U4-01: This module is intentionally thin — all orchestration logic lives in conductor.py.
SEC-03: Structured logging.
"""

from __future__ import annotations

import logging
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

    def run_agent(self, question: str, db_hints: list[str]) -> AgentResult:
        """Run the agent pipeline and return a structured result.

        Parameters
        ----------
        question:
            The user's analytics question (max 4096 characters).
        db_hints:
            Database type hints (e.g. ``["postgres", "duckdb"]``).
            Max 10 items.

        Returns
        -------
        AgentResult
            Always returns — never raises to callers (SEC-15 via conductor).
        """
        logger.info(
            "OracleForgeAgent.run_agent: question=%.80s db_hints=%s",
            question,
            db_hints,
        )
        return self._conductor.run(question, db_hints)


# ---------------------------------------------------------------------------
# Module-level convenience function (FR-01)
# ---------------------------------------------------------------------------


def run_agent(question: str, db_hints: list[str]) -> AgentResult:
    """Module-level convenience wrapper around ``OracleForgeAgent``.

    Creates a fresh agent instance for each call.  For session continuity
    across multiple queries, use the ``OracleForgeAgent`` class directly.

    Parameters
    ----------
    question:
        The user's analytics question (max 4096 characters).
    db_hints:
        Database type hints (e.g. ``["postgres", "duckdb"]``).

    Returns
    -------
    AgentResult
        Always returns — never raises.
    """
    agent = OracleForgeAgent()
    return agent.run_agent(question, db_hints)
