"""DataAgentBench-compatible wrapper interface.

Exposes a stable function signature expected by external harnesses while
reusing the main OracleForge facade.
"""

from __future__ import annotations

from agent.data_agent.oracle_forge_agent import run_agent as _run_agent


def run_agent(question: str, available_databases: list[dict], schema_info: dict) -> dict:
    """Run OracleForge using DAB-style inputs.

    Parameters
    ----------
    question:
        Natural-language analytics question.
    available_databases:
        List of DB descriptors, each containing at least a ``type`` or ``name``.
    schema_info:
        Optional schema metadata provided by harnesses. Included for signature
        compatibility; runtime uses its own context pipeline.
    """
    del schema_info

    hints: list[str] = []
    for db in available_databases or []:
        if not isinstance(db, dict):
            continue
        db_type = str(db.get("type", "")).strip().lower()
        db_name = str(db.get("name", "")).strip().lower()
        if db_type:
            hints.append(db_type)
        elif db_name:
            hints.append(db_name)

    result = _run_agent(question, hints)
    return {
        "answer": result.answer,
        "confidence": result.confidence,
        "query_trace": result.tool_calls,
        "trace_id": result.trace_id,
        "failure_count": result.failure_count,
    }
