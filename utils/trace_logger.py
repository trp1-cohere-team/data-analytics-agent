from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_trace(path: str, record: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("a", encoding="utf-8") as handle:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        handle.write(json.dumps(event) + "\n")
