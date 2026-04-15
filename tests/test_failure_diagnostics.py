"""Unit tests for failure_diagnostics module (U2).

Tests all 4 failure categories, never-raises contract, and DuckDB error_type mapping.
"""

import unittest
import os

os.environ.setdefault("AGENT_OFFLINE_MODE", "1")

from agent.data_agent.failure_diagnostics import classify
from agent.data_agent.types import VALID_FAILURE_CATEGORIES, FailureDiagnosis


class TestClassify(unittest.TestCase):
    """Tests for failure_diagnostics.classify()."""

    def test_returns_failure_diagnosis(self) -> None:
        """classify() always returns a FailureDiagnosis instance."""
        result = classify("syntax error near SELECT", {})
        self.assertIsInstance(result, FailureDiagnosis)

    def test_valid_category(self) -> None:
        """classify() always returns a category from VALID_FAILURE_CATEGORIES."""
        test_cases = [
            ("syntax error near 'FROM'", {}),
            ("column does not exist", {}),
            ("connection refused", {"db_type": "postgres"}),
            ("data not found", {}),
        ]
        for error, context in test_cases:
            result = classify(error, context)
            self.assertIn(result.category, VALID_FAILURE_CATEGORIES)

    def test_query_category_for_syntax_error(self) -> None:
        """SQL syntax errors should classify as 'query'."""
        result = classify("psycopg2.errors.SyntaxError: syntax error at or near 'FROM'", {})
        self.assertEqual(result.category, "query")

    def test_join_key_category(self) -> None:
        """Explicit join key mismatch errors should classify as 'join-key'."""
        result = classify("JOIN mismatch: cannot join tables on foreign key 'book_id'", {})
        self.assertEqual(result.category, "join-key")

    def test_db_type_for_connection_error(self) -> None:
        """Connection errors should classify as 'db-type'."""
        result = classify("connection refused", {"error_type": "config"})
        self.assertEqual(result.category, "db-type")

    def test_duckdb_policy_error_type(self) -> None:
        """DuckDB policy error_type maps to db-type category."""
        result = classify("read_only_violation: only SELECT is permitted", {"error_type": "policy"})
        self.assertEqual(result.category, "db-type")

    def test_duckdb_config_error_type(self) -> None:
        """DuckDB config error_type maps to db-type category."""
        result = classify("duckdb_path_not_found", {"error_type": "config"})
        self.assertEqual(result.category, "db-type")

    def test_duckdb_query_error_type(self) -> None:
        """DuckDB query error_type maps to query category."""
        result = classify("CatalogException: table does not exist", {"error_type": "query"})
        self.assertEqual(result.category, "query")

    def test_never_raises(self) -> None:
        """classify() never raises regardless of input."""
        edge_cases = [
            ("", {}),
            ("x" * 5000, {"error_type": "unknown_type_xyz"}),
            ("", {"error_type": None}),
        ]
        for error, context in edge_cases:
            try:
                result = classify(error, context)
                self.assertIn(result.category, VALID_FAILURE_CATEGORIES)
            except Exception as exc:
                self.fail(f"classify() raised {exc!r} for error={error!r}")

    def test_suggested_fix_is_string(self) -> None:
        """suggested_fix field is always a string."""
        result = classify("any error", {})
        self.assertIsInstance(result.suggested_fix, str)

    def test_explanation_is_string(self) -> None:
        """explanation field is always a string."""
        result = classify("any error", {})
        self.assertIsInstance(result.explanation, str)


if __name__ == "__main__":
    unittest.main()
