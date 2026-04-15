"""Property-based tests for OracleForge Data Agent.

PBT-02: Round-trip serialization properties.
PBT-03: Invariant properties.
PBT-07: Domain-specific Hypothesis generators.
PBT-08: Hypothesis shrinking + reproducibility (default enabled).
PBT-09: Hypothesis framework.

Run: python3 -m unittest tests/test_properties.py -v
"""

import os
import unittest

os.environ.setdefault("AGENT_OFFLINE_MODE", "1")

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from agent.data_agent.types import (
    ContextPacket,
    TraceEvent,
    VALID_FAILURE_CATEGORIES,
)
from agent.data_agent.failure_diagnostics import classify
from eval.score_results import compute_pass_at_1

# ---------------------------------------------------------------------------
# Domain generators (PBT-07: domain-specific, not raw primitives)
# ---------------------------------------------------------------------------

# Generator for valid failure category strings
_category_st = st.sampled_from(sorted(VALID_FAILURE_CATEGORIES))

# Generator for non-empty strings (avoid empty str edge cases in types)
_text_st = st.text(min_size=0, max_size=200)

# Generator for ContextPacket with all fields as bounded text
_context_packet_st = st.builds(
    ContextPacket,
    table_usage=_text_st,
    human_annotations=_text_st,
    institutional_knowledge=_text_st,
    runtime_context=st.fixed_dictionaries({}),
    interaction_memory=_text_st,
    user_question=_text_st,
)

# Generator for TraceEvent
_trace_event_st = st.builds(
    TraceEvent,
    event_type=st.sampled_from(["session_start", "tool_call", "tool_result", "correction", "session_end", "error"]),
    session_id=st.uuids().map(str),
    timestamp=st.just("2026-04-15T00:00:00+00:00"),
    tool_name=_text_st,
    db_type=st.sampled_from(["postgres", "mongodb", "sqlite", "duckdb", ""]),
    input_summary=_text_st,
    outcome=st.sampled_from(["success", "failure", "blocked", "retrying", "complete", ""]),
    diagnosis=_text_st,
    retry_count=st.integers(min_value=0, max_value=10),
    backend=st.sampled_from(["mcp_toolbox", "duckdb_bridge", ""]),
    extra=st.fixed_dictionaries({}),
)

# Generator for trial results list (used in pass@1 invariant)
_trial_result_st = st.fixed_dictionaries({
    "dataset": st.sampled_from(["bookreview", "stockmarket", "yelp"]),
    "query_id": st.sampled_from(["query1", "query2", "query3"]),
    "trial": st.integers(min_value=1, max_value=10),
    "pass": st.booleans(),
})

# Generator for error strings
_error_st = st.one_of(
    st.just(""),
    st.text(min_size=1, max_size=500),
    st.sampled_from([
        "syntax error near SELECT",
        "column does not exist",
        "connection refused",
        "read_only_violation: only SELECT is permitted",
        "duckdb_path_not_found: /tmp/missing.duckdb",
        "CatalogException: table does not exist",
    ]),
)

_context_dict_st = st.fixed_dictionaries({
    "error_type": st.sampled_from(["query", "policy", "config", ""]),
    "db_type": st.sampled_from(["postgres", "mongodb", "sqlite", "duckdb", ""]),
})


# ---------------------------------------------------------------------------
# PBT-02: Round-trip serialization properties
# ---------------------------------------------------------------------------

class TestRoundTripProperties(unittest.TestCase):
    """PBT-02: Round-trip tests for serialization/deserialization pairs."""

    @given(_context_packet_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_context_packet_round_trip(self, packet: ContextPacket) -> None:
        """ContextPacket.to_dict() → from_dict() must reproduce the original."""
        serialized = packet.to_dict()
        restored = ContextPacket.from_dict(serialized)
        self.assertEqual(restored.user_question, packet.user_question)
        self.assertEqual(restored.table_usage, packet.table_usage)
        self.assertEqual(restored.human_annotations, packet.human_annotations)
        self.assertEqual(restored.institutional_knowledge, packet.institutional_knowledge)
        self.assertEqual(restored.interaction_memory, packet.interaction_memory)

    @given(_trace_event_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_trace_event_round_trip(self, event: TraceEvent) -> None:
        """TraceEvent.to_dict() → from_dict() must reproduce the original."""
        serialized = event.to_dict()
        restored = TraceEvent.from_dict(serialized)
        self.assertEqual(restored.event_type, event.event_type)
        self.assertEqual(restored.session_id, event.session_id)
        self.assertEqual(restored.tool_name, event.tool_name)
        self.assertEqual(restored.outcome, event.outcome)
        self.assertEqual(restored.retry_count, event.retry_count)
        self.assertEqual(restored.backend, event.backend)

    @given(_context_packet_st)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_context_packet_to_dict_is_dict(self, packet: ContextPacket) -> None:
        """to_dict() always returns a plain dict."""
        result = packet.to_dict()
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# PBT-03: Invariant properties
# ---------------------------------------------------------------------------

class TestInvariantProperties(unittest.TestCase):
    """PBT-03: Invariant properties that must hold for all valid inputs."""

    @given(_error_st, _context_dict_st)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_failure_classify_always_valid_category(
        self, error: str, context: dict
    ) -> None:
        """failure_diagnostics.classify() MUST always return a valid category.

        PBT-03 invariant: category is always one of the 4 valid values.
        """
        result = classify(error, context)
        self.assertIn(
            result.category,
            VALID_FAILURE_CATEGORIES,
            f"classify() returned invalid category {result.category!r} for error={error!r}",
        )

    @given(_context_packet_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_context_layer6_preserved(self, packet: ContextPacket) -> None:
        """Layer 6 (user_question) must be preserved through to_dict/from_dict."""
        restored = ContextPacket.from_dict(packet.to_dict())
        self.assertEqual(restored.user_question, packet.user_question)

    @given(st.lists(_trial_result_st, min_size=0, max_size=50))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pass_at_1_always_in_range(self, results: list) -> None:
        """compute_pass_at_1() pass@1 score MUST always be in [0.0, 1.0].

        PBT-03 invariant: score range.
        """
        overall, _ = compute_pass_at_1(results)
        self.assertGreaterEqual(overall, 0.0, "pass@1 must be >= 0.0")
        self.assertLessEqual(overall, 1.0, "pass@1 must be <= 1.0")

    @given(_error_st, _context_dict_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_failure_classify_never_raises(
        self, error: str, context: dict
    ) -> None:
        """failure_diagnostics.classify() MUST never raise an exception."""
        try:
            classify(error, context)
        except Exception as exc:
            self.fail(f"classify() raised {exc!r} for error={error!r}")

    @given(_trace_event_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_trace_event_to_dict_contains_required_fields(
        self, event: TraceEvent
    ) -> None:
        """TraceEvent.to_dict() must always include required fields."""
        d = event.to_dict()
        # Only identity fields are always present; optional fields are omitted when empty
        for field in ("event_type", "session_id", "timestamp"):
            self.assertIn(field, d, f"Missing identity field {field!r} in TraceEvent.to_dict()")


if __name__ == "__main__":
    unittest.main()
