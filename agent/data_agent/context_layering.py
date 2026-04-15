"""6-layer context pipeline.

FR-02: Compose all 6 context layers with correct precedence.
Precedence: Layer 6 (user_question, highest) → Layer 1 (table_usage, lowest).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent.data_agent.types import ContextPacket

logger = logging.getLogger(__name__)

# Layer ordering: highest precedence first (used by assemble_prompt)
_LAYER_ORDER = [
    (6, "user_question", "User Question"),
    (5, "interaction_memory", "Interaction Memory"),
    (4, "runtime_context", "Runtime Context"),
    (3, "institutional_knowledge", "Institutional Knowledge"),
    (2, "human_annotations", "Human Annotations"),
    (1, "table_usage", "Table Usage"),
]


def build_context_packet(
    layers: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> ContextPacket:
    """Build a ``ContextPacket`` from a layers dict and/or keyword arguments.

    Keyword arguments override values from the *layers* dict.

    Parameters
    ----------
    layers : dict | None
        Mapping of layer field names to values.
    **kwargs
        Additional overrides (take highest priority).
    """
    merged: dict[str, Any] = {}
    if layers:
        merged.update(layers)
    merged.update(kwargs)

    return ContextPacket(
        table_usage=str(merged.get("table_usage", "")),
        human_annotations=str(merged.get("human_annotations", "")),
        institutional_knowledge=str(merged.get("institutional_knowledge", "")),
        runtime_context=merged.get("runtime_context", {}),
        interaction_memory=str(merged.get("interaction_memory", "")),
        user_question=str(merged.get("user_question", "")),
    )


def assemble_prompt(packet: ContextPacket) -> str:
    """Assemble context layers into a single prompt string.

    Layers are ordered by precedence — Layer 6 (user_question) first,
    Layer 1 (table_usage) last.  Empty layers are omitted.

    The ``runtime_context`` dict is serialised to human-readable
    key-value pairs.
    """
    sections: list[str] = []

    for _num, field_name, display_name in _LAYER_ORDER:
        value = getattr(packet, field_name, None)

        if field_name == "runtime_context":
            if not value:
                continue
            formatted = _format_runtime_context(value)
            if formatted:
                sections.append(f"## {display_name}\n{formatted}")
        else:
            if not value:
                continue
            sections.append(f"## {display_name}\n{value}")

    return "\n\n".join(sections)


def _format_runtime_context(ctx: dict) -> str:
    """Format the runtime_context dict for prompt inclusion."""
    if not ctx:
        return ""

    lines: list[str] = []
    for key, val in ctx.items():
        if isinstance(val, (list, dict)):
            lines.append(f"- **{key}**: {json.dumps(val, default=str)}")
        else:
            lines.append(f"- **{key}**: {val}")
    return "\n".join(lines)
