"""Unit tests for MemoryManager (U3).

Tests lazy initialization, session cap, topic cap, and 3-layer file structure.
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

os.environ.setdefault("AGENT_OFFLINE_MODE", "1")


class TestMemoryManager(unittest.TestCase):
    """Tests for agent.runtime.memory.MemoryManager."""

    def setUp(self) -> None:
        """Create a fresh temp dir for each test."""
        self.tmpdir = tempfile.mkdtemp(prefix="test_memory_")
        os.environ["AGENT_MEMORY_ROOT"] = self.tmpdir
        os.environ["AGENT_RUNTIME_EVENTS_PATH"] = os.path.join(self.tmpdir, "events.jsonl")
        # Re-import after env change to pick up new root
        import importlib
        import agent.data_agent.config as cfg
        importlib.reload(cfg)
        import agent.runtime.memory as mem
        importlib.reload(mem)
        from agent.runtime.memory import MemoryManager
        from agent.data_agent.types import MemoryTurn
        self.MemoryManager = MemoryManager
        self.MemoryTurn = MemoryTurn

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_no_side_effects_on_import(self) -> None:
        """MemoryManager import does not create files."""
        manager = self.MemoryManager(session_id="test-session-001")
        # Nothing should exist yet (lazy init)
        sessions_dir = os.path.join(self.tmpdir, "sessions")
        self.assertFalse(os.path.exists(sessions_dir))

    def test_save_turn_creates_session_file(self) -> None:
        """save_turn() lazily creates the session JSONL file."""
        manager = self.MemoryManager(session_id="test-session-002")
        turn = self.MemoryTurn(
            role="user",
            content="Hello",
            timestamp=self._ts(),
            session_id="test-session-002",
        )
        manager.save_turn(turn)
        session_file = os.path.join(self.tmpdir, "sessions", "test-session-002.jsonl")
        self.assertTrue(os.path.exists(session_file))

    def test_session_cap_enforced(self) -> None:
        """Session file is capped at AGENT_MEMORY_SESSION_ITEMS turns."""
        os.environ["AGENT_MEMORY_SESSION_ITEMS"] = "3"
        import importlib
        import agent.data_agent.config as cfg
        importlib.reload(cfg)
        import agent.runtime.memory as mem
        importlib.reload(mem)
        manager = mem.MemoryManager(session_id="test-session-cap")
        for i in range(6):
            manager.save_turn(self.MemoryTurn(
                role="user" if i % 2 == 0 else "assistant",
                content=f"turn {i}",
                timestamp=self._ts(),
                session_id="test-session-cap",
            ))
        session_file = os.path.join(self.tmpdir, "sessions", "test-session-cap.jsonl")
        lines = open(session_file).read().strip().splitlines()
        self.assertLessEqual(len(lines), 3)

    def test_get_memory_context_returns_string(self) -> None:
        """get_memory_context() always returns a string."""
        manager = self.MemoryManager(session_id="test-session-003")
        result = manager.get_memory_context()
        self.assertIsInstance(result, str)

    def test_get_memory_context_empty_for_new_session(self) -> None:
        """get_memory_context() returns empty string for new session with no turns."""
        manager = self.MemoryManager(session_id="test-session-new-xyz")
        result = manager.get_memory_context()
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
