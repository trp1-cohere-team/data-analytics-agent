"""Unit tests for context_layering module (U2).

Tests 6-layer context assembly, precedence rules, and prompt format.
"""

import unittest
import os

os.environ.setdefault("AGENT_OFFLINE_MODE", "1")

from agent.data_agent.context_layering import build_context_packet, assemble_prompt
from agent.data_agent.types import ContextPacket


class TestBuildContextPacket(unittest.TestCase):
    """Tests for build_context_packet()."""

    def test_all_layers_populated(self) -> None:
        """All 6 context layers appear in the ContextPacket."""
        packet = build_context_packet(
            user_question="What is the average rating?",
            interaction_memory="Previous question about books",
            runtime_context={"session_id": "test-001"},
            institutional_knowledge="Agent rules",
            human_annotations="Schema hint: use rating_number",
            table_usage="query_postgresql: Execute SQL",
        )
        self.assertIsInstance(packet, ContextPacket)
        self.assertEqual(packet.user_question, "What is the average rating?")
        self.assertEqual(packet.interaction_memory, "Previous question about books")
        self.assertEqual(packet.institutional_knowledge, "Agent rules")
        self.assertEqual(packet.human_annotations, "Schema hint: use rating_number")
        self.assertEqual(packet.table_usage, "query_postgresql: Execute SQL")

    def test_layer6_is_user_question(self) -> None:
        """Layer 6 (user_question) is the highest priority."""
        packet = build_context_packet(
            user_question="The critical question",
            table_usage="Low priority schema info",
        )
        # Layer 6 (user_question) should always be present and non-empty
        self.assertEqual(packet.user_question, "The critical question")

    def test_empty_layers_default_to_empty_string(self) -> None:
        """Missing layers default to empty strings."""
        packet = build_context_packet(user_question="test?")
        self.assertEqual(packet.interaction_memory, "")
        self.assertEqual(packet.institutional_knowledge, "")
        self.assertEqual(packet.human_annotations, "")
        self.assertEqual(packet.table_usage, "")

    def test_backward_compat_aliases(self) -> None:
        """Backward-compat property aliases work correctly."""
        packet = build_context_packet(
            user_question="test",
            table_usage="schema info",
            human_annotations="annotation",
            institutional_knowledge="knowledge",
        )
        self.assertEqual(packet.schema_and_metadata, "schema info")
        self.assertIn("annotation", packet.institutional_and_domain)
        self.assertIn("knowledge", packet.institutional_and_domain)


class TestAssemblePrompt(unittest.TestCase):
    """Tests for assemble_prompt()."""

    def test_prompt_contains_question(self) -> None:
        """Assembled prompt must contain the user question."""
        packet = ContextPacket(user_question="What is the top genre?")
        prompt = assemble_prompt(packet)
        self.assertIn("What is the top genre?", prompt)

    def test_prompt_is_string(self) -> None:
        """assemble_prompt always returns a string."""
        packet = ContextPacket()
        result = assemble_prompt(packet)
        self.assertIsInstance(result, str)

    def test_prompt_includes_schema_when_present(self) -> None:
        """Schema info (Layer 1) appears in assembled prompt."""
        packet = ContextPacket(
            user_question="test",
            table_usage="query_postgresql: Execute SQL against PostgreSQL",
        )
        prompt = assemble_prompt(packet)
        self.assertIn("query_postgresql", prompt)

    def test_empty_packet_returns_string(self) -> None:
        """An empty context packet returns a string (may be empty)."""
        packet = ContextPacket()
        prompt = assemble_prompt(packet)
        self.assertIsInstance(prompt, str)


if __name__ == "__main__":
    unittest.main()
