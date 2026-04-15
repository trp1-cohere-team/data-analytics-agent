"""Trace event builder utilities.

Factory functions for constructing ``TraceEvent`` instances with sensible defaults
and a human-readable summary formatter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.data_agent.types import TraceEvent


def build_trace_event(
    event_type: str,
    session_id: str,
    *,
    timestamp: str = "",
    tool_name: str = "",
    db_type: str = "",
    input_summary: str = "",
    outcome: str = "",
    diagnosis: str = "",
    retry_count: int = 0,
    backend: str = "",
    extra: dict[str, Any] | None = None,
) -> TraceEvent:
    """Build a ``TraceEvent`` with defaults filled in.

    *timestamp* defaults to the current UTC time in ISO 8601 format.
    """
    return TraceEvent(
        event_type=event_type,
        session_id=session_id,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        tool_name=tool_name,
        db_type=db_type,
        input_summary=input_summary,
        outcome=outcome,
        diagnosis=diagnosis,
        retry_count=retry_count,
        backend=backend,
        extra=extra if extra is not None else {},
    )


def format_trace_summary(events: list[TraceEvent]) -> str:
    """Return a human-readable multi-line summary of *events*.

    Groups events by ``session_id`` and formats each as:
    ``[timestamp] event_type: tool_name (outcome) retry=N``
    """
    if not events:
        return "(no events)"

    lines: list[str] = []
    current_session: str = ""

    for ev in events:
        if ev.session_id != current_session:
            current_session = ev.session_id
            lines.append(f"\n--- session {current_session} ---")

        parts = [f"[{ev.timestamp}]", ev.event_type]
        if ev.tool_name:
            parts.append(f": {ev.tool_name}")
        if ev.outcome:
            parts.append(f"({ev.outcome})")
        if ev.retry_count > 0:
            parts.append(f"retry={ev.retry_count}")
        if ev.backend:
            parts.append(f"[{ev.backend}]")
        lines.append(" ".join(parts))

    return "\n".join(lines)
