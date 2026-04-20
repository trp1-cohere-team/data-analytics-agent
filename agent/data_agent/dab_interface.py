"""DataAgentBench-compatible wrapper interface.

Exposes a stable function signature expected by external harnesses while
reusing the main OracleForge facade. Forwards dataset-level schema and
hint information into the conductor's context layer so the LLM can write
analytic SQL directly instead of rediscovering the schema.
"""

from __future__ import annotations

from typing import Any

from agent.data_agent.oracle_forge_agent import run_agent as _run_agent


def run_agent(
    question: str,
    available_databases: list[dict],
    schema_info: dict | None = None,
) -> dict:
    """Run OracleForge using DAB-style inputs.

    Parameters
    ----------
    question:
        Natural-language analytics question.
    available_databases:
        List of DB descriptors; each entry should carry at least a ``type``
        or ``name``. These feed both the type hints (used for tool
        selection) and the prompt's DATASET CONTEXT block.
    schema_info:
        Optional metadata from the harness. Accepted keys:
        ``db_description`` (str), ``hints`` (str), ``dataset`` (str).
        Kept as a dict so future harnesses can pass richer context
        without breaking the wire format.
    """
    schema_info = schema_info or {}

    hints: list[str] = []
    descriptors: list[dict[str, str]] = []
    for db in available_databases or []:
        if not isinstance(db, dict):
            continue
        db_type = str(db.get("type", "")).strip().lower()
        db_name = str(db.get("name", "")).strip()
        if db_type:
            hints.append(db_type)
        elif db_name:
            hints.append(db_name.lower())
        descriptors.append({"type": db_type, "name": db_name})

    # Preserve type-hint order/duplication so downstream tool selection stays
    # stable across callers that already rely on ``db.type`` priority.
    dataset_context: dict[str, Any] = {
        "dataset": str(schema_info.get("dataset", "")).strip(),
        "available_databases": descriptors,
        "db_description": str(schema_info.get("db_description", "")).strip(),
        "hints": str(schema_info.get("hints", "")).strip(),
    }

    result = _run_agent(question, hints, dataset_context)
    return {
        "answer": result.answer,
        "confidence": result.confidence,
        "query_trace": result.tool_calls,
        "trace_id": result.trace_id,
        "failure_count": result.failure_count,
    }
