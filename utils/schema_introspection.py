from __future__ import annotations

from typing import Any


def summarize_schema(schema_info: dict[str, Any]) -> str:
    if not schema_info:
        return "No schema info provided."

    lines: list[str] = []
    for db_name, objects in schema_info.items():
        if isinstance(objects, list):
            preview = ", ".join(str(item) for item in objects[:8])
            lines.append(f"- {db_name}: {preview}")
        else:
            lines.append(f"- {db_name}: {objects}")

    return "\n".join(lines)
