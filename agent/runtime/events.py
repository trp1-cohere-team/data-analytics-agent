"""Append-only JSONL event ledger.

FR-06: Every tool call emits a structured JSONL event.
SEC-13: JSON parsing with try/except; no pickle/eval.
SEC-15: Explicit error handling on all file I/O; resource cleanup via context managers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from agent.data_agent.types import TraceEvent
from agent.data_agent.config import AGENT_RUNTIME_EVENTS_PATH

logger = logging.getLogger(__name__)


def emit_event(
    event: TraceEvent,
    path: Optional[str] = None,
) -> None:
    """Append a single TraceEvent as a JSONL line to the event ledger.

    Creates parent directories and the file lazily on first write.
    Validates event structure before writing (SEC-13).
    """
    target = path or AGENT_RUNTIME_EVENTS_PATH

    # Validate required fields
    if not event.event_type:
        logger.warning("emit_event: event_type is empty — skipping")
        return
    if not event.session_id:
        logger.warning("emit_event: session_id is empty — skipping")
        return
    if not event.timestamp:
        logger.warning("emit_event: timestamp is empty — skipping")
        return

    try:
        data = event.to_dict()
        line = json.dumps(data, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        logger.warning("emit_event: serialization failed — %s", exc)
        return

    try:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        logger.warning("emit_event: I/O error writing to %s — %s", target, exc)


def read_events(path: Optional[str] = None) -> list[TraceEvent]:
    """Read all events from the JSONL ledger.

    Skips malformed lines with a warning (SEC-13).
    Returns an empty list if the file does not exist.
    """
    target = path or AGENT_RUNTIME_EVENTS_PATH
    events: list[TraceEvent] = []

    if not os.path.isfile(target):
        return events

    try:
        with open(target, "r", encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                    events.append(TraceEvent.from_dict(data))
                except (json.JSONDecodeError, TypeError, KeyError) as exc:
                    logger.warning(
                        "read_events: skipping malformed line %d — %s", lineno, exc
                    )
    except OSError as exc:
        logger.warning("read_events: I/O error reading %s — %s", target, exc)

    return events
