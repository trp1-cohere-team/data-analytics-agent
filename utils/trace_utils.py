"""Trace event builder utilities.

Factory functions for constructing ``TraceEvent`` instances with sensible defaults
and a human-readable summary formatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceEvent:
    """Standalone trace event model for utility-layer reuse.

    Intentionally mirrors the runtime event payload shape but does not depend
    on any agent modules, so this utility can be reused in isolation.
    """

    event_type: str
    session_id: str
    timestamp: str
    tool_name: str = ""
    db_type: str = ""
    input_summary: str = ""
    outcome: str = ""
    diagnosis: str = ""
    retry_count: int = 0
    backend: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.db_type:
            d["db_type"] = self.db_type
        if self.input_summary:
            d["input_summary"] = self.input_summary
        if self.outcome:
            d["outcome"] = self.outcome
        if self.diagnosis:
            d["diagnosis"] = self.diagnosis
        if self.retry_count:
            d["retry_count"] = self.retry_count
        if self.backend:
            d["backend"] = self.backend
        if self.extra:
            d["extra"] = self.extra
        return d


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
