"""Unit tests for OracleForgeConductor (U3).

NFR-05: All tests pass with python3 -m unittest discover -s tests -v.
Tests the offline pipeline end-to-end and key conductor behaviors.
"""

import unittest
import os
from unittest.mock import patch

os.environ.setdefault("AGENT_OFFLINE_MODE", "1")

from agent.data_agent.types import AgentResult, InvokeResult
from agent.runtime.conductor import OracleForgeConductor


class TestConductorOffline(unittest.TestCase):
    """Offline pipeline smoke tests for OracleForgeConductor."""

    def setUp(self) -> None:
        self.conductor = OracleForgeConductor(session_id="test-conductor-001")

    def test_run_returns_agent_result(self) -> None:
        """run() must return an AgentResult instance."""
        result = self.conductor.run("How many books are there?", ["postgres"])
        self.assertIsInstance(result, AgentResult)

    def test_result_fields_populated(self) -> None:
        """All AgentResult fields must be populated."""
        result = self.conductor.run("What is the top category?", ["sqlite"])
        self.assertIsInstance(result.answer, str)
        self.assertGreater(len(result.answer), 0)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        self.assertIsInstance(result.trace_id, str)
        self.assertIsInstance(result.tool_calls, list)
        self.assertGreaterEqual(result.failure_count, 0)

    def test_empty_db_hints(self) -> None:
        """run() handles empty db_hints without crashing."""
        result = self.conductor.run("test question", [])
        self.assertIsInstance(result, AgentResult)

    def test_invalid_question_too_long(self) -> None:
        """Questions exceeding 4096 chars return an error result."""
        long_q = "x" * 5000
        result = self.conductor.run(long_q, ["postgres"])
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.confidence, 0.0)

    def test_invalid_db_hints_too_many(self) -> None:
        """More than 10 db_hints returns an error result."""
        result = self.conductor.run("test", ["db"] * 11)
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.confidence, 0.0)

    def test_global_error_handler_safety(self) -> None:
        """run() never raises — global handler catches all exceptions."""
        # Pass a non-list for db_hints to trigger validation; should not raise
        result = self.conductor.run("test", "not_a_list")  # type: ignore
        self.assertIsInstance(result, AgentResult)

    def test_multiple_runs_independent(self) -> None:
        """Multiple run() calls on same conductor return independent results."""
        r1 = self.conductor.run("Question one?", ["postgres"])
        r2 = self.conductor.run("Question two?", ["sqlite"])
        self.assertIsInstance(r1, AgentResult)
        self.assertIsInstance(r2, AgentResult)

    def test_extract_tool_call_recovers_trailing_brace(self) -> None:
        """Parser should recover a valid tool call from near-JSON output."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": (
                            'TOOL_CALL: {"tool": "query_sqlite", '
                            '"parameters": {"sql": "SELECT 1"}}}'
                        )
                    }
                }
            ]
        }
        tool_call = OracleForgeConductor._extract_tool_call(response)
        self.assertIsNotNone(tool_call)
        self.assertEqual(tool_call.get("tool"), "query_sqlite")
        self.assertEqual(tool_call.get("parameters", {}).get("sql"), "SELECT 1")

    def test_run_ignores_malformed_tool_call_text_and_continues(self) -> None:
        """Malformed TOOL_CALL text should not terminate the run prematurely."""
        malformed = {
            "choices": [{"message": {"content": "TOOL_CALL: {tool: query_sqlite}"}}]
        }
        valid_call = {
            "choices": [
                {
                    "message": {
                        "content": (
                            'TOOL_CALL: {"tool": "query_sqlite", '
                            '"parameters": {"sql": "SELECT 1"}}'
                        )
                    }
                }
            ]
        }
        final_answer = {"choices": [{"message": {"content": "ANSWER: final answer"}}]}

        invoke_ok = InvokeResult(
            success=True,
            tool_name="query_sqlite",
            result=[{"n": 1}],
            error="",
            error_type="",
            db_type="sqlite",
        )

        with patch.object(
            self.conductor,
            "_call_llm",
            side_effect=[malformed, valid_call, final_answer],
        ):
            with patch.object(self.conductor._mcp, "invoke_tool", return_value=invoke_ok):
                result = self.conductor.run("test", ["sqlite"])

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.answer, "final answer")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertFalse(result.answer.startswith("TOOL_CALL:"))

    def test_query_recovery_rewrites_quoted_identifier(self) -> None:
        """Query-category recovery should rewrite common spaced identifiers."""
        seeded = self.conductor._recover_query_syntax(  # pylint: disable=protected-access
            "query_duckdb",
            {"sql": "SELECT MAX(Adj Close) FROM REAL;"},
        )
        self.assertIsNotNone(seeded)
        tool_name, params = seeded
        self.assertEqual(tool_name, "query_duckdb")
        self.assertIn('"Adj Close"', params.get("sql", ""))

    def test_join_key_recovery_resolves_using_clause(self) -> None:
        """Join-key recovery should replace USING(...) with explicit ON join key."""
        sql = (
            "SELECT * FROM orders o "
            "JOIN customers c USING (bad_key) "
            "WHERE o.amount > 0"
        )
        with patch.object(
            self.conductor,
            "_schema_columns_for_table",
            side_effect=[["customer_id", "amount"], ["customer_id", "name"]],
        ):
            seeded = self.conductor._recover_join_key(  # pylint: disable=protected-access
                "query_postgresql",
                {"sql": sql},
            )
        self.assertIsNotNone(seeded)
        _tool_name, params = seeded
        rewritten = params.get("sql", "")
        self.assertIn("ON o.customer_id = c.customer_id", rewritten)
        self.assertNotIn("USING (bad_key)", rewritten)

    def test_db_type_recovery_reroutes_tool(self) -> None:
        """DB-type recovery should reroute SQL payload to the inferred backend."""
        seeded = self.conductor._recover_db_type(  # pylint: disable=protected-access
            "query_sqlite",
            {"sql": "SELECT * FROM AAPL"},
            "wrong database dialect: use DuckDB for this table",
            {"db_type": "sqlite"},
        )
        self.assertIsNotNone(seeded)
        tool_name, params = seeded
        self.assertEqual(tool_name, "query_duckdb")
        self.assertIn("SELECT * FROM AAPL", params.get("sql", ""))

    def test_data_quality_recovery_builds_count_probe(self) -> None:
        """Data-quality recovery should use a COUNT probe over the prior SQL."""
        seeded = self.conductor._recover_data_quality(  # pylint: disable=protected-access
            "query_postgresql",
            {"sql": "SELECT id FROM users WHERE status = 'active';"},
        )
        self.assertIsNotNone(seeded)
        tool_name, params = seeded
        self.assertEqual(tool_name, "query_postgresql")
        self.assertIn("SELECT COUNT(*) AS row_count", params.get("sql", ""))

    def test_sanitize_rejects_preview_style_result(self) -> None:
        """Preview summaries must not be treated as final user answers."""
        cleaned = OracleForgeConductor._sanitize_answer(
            "Found 2,792 result(s). First 5 table_name(s): AAAU, AADR, AAME, AAWW, AAXJ.",
            "Which repo has the most copies?",
        )
        self.assertEqual(cleaned, "")

    def test_run_retries_when_llm_returns_preview_style_answer(self) -> None:
        """A preview-style ANSWER should be rejected and retried within the loop."""
        tool_call = {
            "choices": [
                {
                    "message": {
                        "content": (
                            'TOOL_CALL: {"tool": "query_sqlite", '
                            '"parameters": {"sql": "SELECT 1 AS n"}}'
                        )
                    }
                }
            ]
        }
        preview_answer = {
            "choices": [
                {
                    "message": {
                        "content": "ANSWER: Found 1 result(s). First 1 n(s): 1."
                    }
                }
            ]
        }
        final_answer = {"choices": [{"message": {"content": "ANSWER: 1"}}]}

        invoke_ok = InvokeResult(
            success=True,
            tool_name="query_sqlite",
            result=[{"n": 1}],
            error="",
            error_type="",
            db_type="sqlite",
        )

        with patch.object(
            self.conductor,
            "_call_llm",
            side_effect=[tool_call, preview_answer, final_answer],
        ):
            with patch.object(self.conductor._mcp, "invoke_tool", return_value=invoke_ok):
                result = self.conductor.run("Return n", ["sqlite"])

        self.assertEqual(result.answer, "1")
        self.assertEqual(len(result.tool_calls), 1)

    def test_finalize_result_drops_unsanitized_preview_output(self) -> None:
        """Finalizer should never leak sanitizer-rejected preview output."""
        self.conductor._eval_mode = True  # pylint: disable=protected-access
        result = self.conductor._finalize_result(  # pylint: disable=protected-access
            question="test",
            answer_text="Found 24 result(s). First 5 table_name(s): a, b, c, d, e.",
            confidence=0.5,
        )
        self.assertIn("not able to produce a reliable answer", result.answer.lower())
        self.assertNotIn("Found 24 result(s)", result.answer)


if __name__ == "__main__":
    unittest.main()
