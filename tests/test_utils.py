"""Unit tests for shared utility modules in utils/."""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from utils.db_utils import db_type_from_kind, sanitize_sql_for_log, validate_db_url
from utils.text_utils import (
    extract_keywords,
    filename_stem_overlap,
    freshness_bonus,
    score_overlap,
)
from utils.trace_utils import TraceEvent, build_trace_event, format_trace_summary


class TestDbUtils(unittest.TestCase):
    def test_db_type_from_kind(self) -> None:
        self.assertEqual(db_type_from_kind("postgres-sql"), "postgres")
        self.assertEqual(db_type_from_kind("duckdb_bridge_sql"), "duckdb")
        self.assertEqual(db_type_from_kind("unknown-kind"), "unknown")

    def test_validate_db_url(self) -> None:
        self.assertTrue(validate_db_url("postgresql://u:p@h:5432/db", "postgres"))
        self.assertTrue(validate_db_url("mongodb://localhost:27017", "mongodb"))
        self.assertFalse(validate_db_url("", "postgres"))

    def test_sanitize_sql_for_log(self) -> None:
        sql = "SELECT * FROM t WHERE id = 42 AND name = 'Ada'"
        out = sanitize_sql_for_log(sql)
        self.assertIn("<NUM>", out)
        self.assertIn("<STR>", out)


class TestTextUtils(unittest.TestCase):
    def test_extract_keywords(self) -> None:
        kws = extract_keywords("What is the average volume in 2019?")
        self.assertIn("average", kws)
        self.assertIn("volume", kws)

    def test_score_overlap(self) -> None:
        kws = ["duckdb", "volume"]
        self.assertGreater(score_overlap(kws, "duckdb table with volume stats"), 0.0)

    def test_filename_stem_overlap(self) -> None:
        kws = ["query", "patterns"]
        s = filename_stem_overlap(kws, "/tmp/query-patterns.md")
        self.assertGreater(s, 0.0)

    def test_freshness_bonus(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            path = fh.name
        try:
            os.utime(path, (time.time(), time.time()))
            self.assertGreaterEqual(freshness_bonus(path), 0.1)
        finally:
            os.unlink(path)


class TestTraceUtils(unittest.TestCase):
    def test_build_trace_event(self) -> None:
        ev = build_trace_event(event_type="tool_call", session_id="s1", tool_name="query_sqlite")
        self.assertIsInstance(ev, TraceEvent)
        self.assertEqual(ev.tool_name, "query_sqlite")

    def test_format_trace_summary(self) -> None:
        ev1 = build_trace_event(event_type="session_start", session_id="s2")
        ev2 = build_trace_event(event_type="tool_result", session_id="s2", outcome="success")
        text = format_trace_summary([ev1, ev2])
        self.assertIn("session s2", text)
        self.assertIn("tool_result", text)


if __name__ == "__main__":
    unittest.main()
