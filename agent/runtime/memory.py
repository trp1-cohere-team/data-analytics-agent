"""3-layer persistent memory system.

FR-05: file-based memory with index, topics, and session transcripts.
Lazy initialization — zero side effects on import or __init__.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from agent.data_agent.config import (
    AGENT_MEMORY_ROOT,
    AGENT_MEMORY_SESSION_ITEMS,
    AGENT_MEMORY_TOPIC_CHARS,
)
from agent.data_agent.types import MemoryTurn

logger = logging.getLogger(__name__)


class MemoryManager:
    """3-layer file-based memory manager.

    - Layer 1: ``index.json`` — topic → file mapping
    - Layer 2: ``topics/<key>.md`` — condensed topic knowledge
    - Layer 3: ``sessions/<session_id>.jsonl`` — turn-by-turn transcript
    """

    def __init__(self, root: Optional[str] = None, session_id: str = "") -> None:
        self._root = root or AGENT_MEMORY_ROOT
        self._session_id = session_id
        self._index_path = os.path.join(self._root, "index.json")
        self._topics_dir = os.path.join(self._root, "topics")
        self._sessions_dir = os.path.join(self._root, "sessions")

    # ------------------------------------------------------------------
    # Session transcript (Layer 3)
    # ------------------------------------------------------------------

    def _session_path(self) -> str:
        return os.path.join(self._sessions_dir, f"{self._session_id}.jsonl")

    def load_session(self) -> list[MemoryTurn]:
        """Read session transcript.  Returns empty list if not found."""
        path = self._session_path()
        if not os.path.isfile(path):
            return []

        turns: list[MemoryTurn] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for lineno, raw in enumerate(fh, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                        turns.append(
                            MemoryTurn(
                                role=data["role"],
                                content=data["content"],
                                timestamp=data["timestamp"],
                                session_id=data["session_id"],
                            )
                        )
                    except (json.JSONDecodeError, KeyError, ValueError) as exc:
                        logger.warning("memory: skipping malformed turn line %d: %s", lineno, exc)
        except OSError as exc:
            logger.warning("memory: failed to read session %s: %s", path, exc)

        return turns

    def save_turn(self, turn: MemoryTurn) -> None:
        """Append a turn, enforcing the session cap."""
        try:
            os.makedirs(self._sessions_dir, exist_ok=True)
        except OSError as exc:
            logger.warning("memory: failed to create sessions dir: %s", exc)
            return

        turns = self.load_session()
        turns.append(turn)

        # Trim oldest if over cap
        if len(turns) > AGENT_MEMORY_SESSION_ITEMS:
            turns = turns[-AGENT_MEMORY_SESSION_ITEMS:]

        path = self._session_path()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                for t in turns:
                    line = json.dumps(
                        {
                            "role": t.role,
                            "content": t.content,
                            "timestamp": t.timestamp,
                            "session_id": t.session_id,
                        },
                        separators=(",", ":"),
                    )
                    fh.write(line + "\n")
        except OSError as exc:
            logger.warning("memory: failed to write session %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Topic knowledge (Layer 2)
    # ------------------------------------------------------------------

    def load_topic(self, key: str) -> str:
        """Read topic content.  Returns empty string if not found."""
        path = os.path.join(self._topics_dir, f"{key}.md")
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            logger.warning("memory: failed to read topic %s: %s", key, exc)
            return ""

    def save_topic(self, key: str, content: str) -> None:
        """Write topic content, enforcing the char cap."""
        try:
            os.makedirs(self._topics_dir, exist_ok=True)
        except OSError as exc:
            logger.warning("memory: failed to create topics dir: %s", exc)
            return

        truncated = content[:AGENT_MEMORY_TOPIC_CHARS]
        path = os.path.join(self._topics_dir, f"{key}.md")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(truncated)
        except OSError as exc:
            logger.warning("memory: failed to write topic %s: %s", key, exc)
            return

        # Update index
        self._update_index(key, f"{key}.md")

    # ------------------------------------------------------------------
    # Topic index (Layer 1)
    # ------------------------------------------------------------------

    def get_index(self) -> dict[str, str]:
        """Return the topic index mapping."""
        if not os.path.isfile(self._index_path):
            return {}
        try:
            with open(self._index_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("memory: failed to read index: %s", exc)
            return {}

    def _update_index(self, key: str, filename: str) -> None:
        """Add or update a topic in the index."""
        index = self.get_index()
        index[key] = filename
        try:
            os.makedirs(os.path.dirname(self._index_path) or ".", exist_ok=True)
            with open(self._index_path, "w", encoding="utf-8") as fh:
                json.dump(index, fh, indent=2)
        except OSError as exc:
            logger.warning("memory: failed to write index: %s", exc)

    # ------------------------------------------------------------------
    # Assembled memory context (for Layer 5)
    # ------------------------------------------------------------------

    def get_memory_context(self) -> str:
        """Assemble memory for context Layer 5 (interaction_memory)."""
        parts: list[str] = []

        # Session transcript excerpt
        turns = self.load_session()
        if turns:
            lines = [f"[{t.role}] {t.content}" for t in turns[-6:]]
            parts.append("### Recent Conversation\n" + "\n".join(lines))

        # Topic summaries
        index = self.get_index()
        if index:
            summaries: list[str] = []
            for key in list(index.keys())[:10]:
                content = self.load_topic(key)
                if content:
                    summaries.append(f"**{key}**: {content[:200]}")
            if summaries:
                parts.append("### Remembered Topics\n" + "\n".join(summaries))

        return "\n\n".join(parts)
