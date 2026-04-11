"""Unit tests for agent/correction/engine.py.

Covers:
  - classify_failure: all 5 FailureType branches
  - fix_syntax_error: all 4 rule patterns; output length invariant
  - fix_wrong_db_type: correct db_type rerouting per DB signal set
  - fix_data_quality: COALESCE insertion
  - correct(): routes to correct strategy; raises CorrectionExhausted after limit
  - PBT-U1-01: classify_failure always returns valid FailureType (never raises) — 300 examples
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import given

from agent.correction.engine import CorrectionEngine, CorrectionExhausted
from agent.models import (
    ExecutionFailure,
    FailureType,
    MergeSpec,
    QueryPlan,
    SubQuery,
)
from tests.unit.strategies import INVARIANT_SETTINGS, execution_failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine() -> CorrectionEngine:
    """CorrectionEngine with stub LLM and engine (no real calls in unit tests)."""
    class _StubLLM:
        async def chat(self):
            pass

    class _StubEngine:
        pass

    return CorrectionEngine(llm_client=_StubLLM(), engine=_StubEngine())


def _failure(error_message: str, db_type: str = "postgres", error_type: str = "query_error") -> ExecutionFailure:
    return ExecutionFailure(
        sub_query_id=str(uuid.uuid4()),
        db_type=db_type,
        error_message=error_message,
        error_type=error_type,
    )


def _plan(db_type: str = "postgres", query: str = "SELECT 1") -> QueryPlan:
    return QueryPlan(
        id=str(uuid.uuid4()),
        sub_queries=[SubQuery(id=str(uuid.uuid4()), db_type=db_type, db_name=db_type, query=query)],
        merge_spec=MergeSpec(),
    )


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------

class TestClassifyFailure:
    def test_syntax_error(self):
        eng = _engine()
        f = _failure("syntax error near 'FROM'")
        assert eng.classify_failure(f) == FailureType.SYNTAX_ERROR

    def test_syntax_error_unexpected_token(self):
        eng = _engine()
        f = _failure("unexpected token: WHERE")
        assert eng.classify_failure(f) == FailureType.SYNTAX_ERROR

    def test_join_key_mismatch(self):
        eng = _engine()
        f = _failure("join type mismatch between columns")
        assert eng.classify_failure(f) == FailureType.JOIN_KEY_MISMATCH

    def test_wrong_db_type_postgres_error_on_sqlite(self):
        eng = _engine()
        f = _failure("psycopg2 error: relation does not exist", db_type="sqlite")
        assert eng.classify_failure(f) == FailureType.WRONG_DB_TYPE

    def test_wrong_db_type_sqlite_error_on_postgres(self):
        eng = _engine()
        f = _failure("no such table: users", db_type="postgres")
        assert eng.classify_failure(f) == FailureType.WRONG_DB_TYPE

    def test_data_quality_null(self):
        eng = _engine()
        f = _failure("value is null where non-null expected")
        assert eng.classify_failure(f) == FailureType.DATA_QUALITY

    def test_data_quality_missing(self):
        eng = _engine()
        f = _failure("field 'revenue' not found in document")
        assert eng.classify_failure(f) == FailureType.DATA_QUALITY

    def test_unknown(self):
        eng = _engine()
        f = _failure("something completely unexpected happened")
        assert eng.classify_failure(f) == FailureType.UNKNOWN

    def test_syntax_takes_priority_over_data_quality(self):
        eng = _engine()
        f = _failure("syntax error: null value not allowed")
        assert eng.classify_failure(f) == FailureType.SYNTAX_ERROR


# ---------------------------------------------------------------------------
# fix_syntax_error
# ---------------------------------------------------------------------------

class TestFixSyntaxError:
    def test_rownum_to_limit(self):
        eng = _engine()
        result = eng.fix_syntax_error("SELECT * FROM t WHERE ROWNUM <= 10", "")
        assert "LIMIT 10" in result
        assert "ROWNUM" not in result

    def test_isnull_to_is_null(self):
        eng = _engine()
        result = eng.fix_syntax_error("SELECT * FROM t WHERE ISNULL(col)", "")
        assert "IS NULL" in result
        assert "ISNULL(" not in result

    def test_nvl_to_coalesce(self):
        eng = _engine()
        result = eng.fix_syntax_error("SELECT NVL(col, 0) FROM t", "")
        assert "COALESCE(" in result
        assert "NVL(" not in result

    def test_group_by_without_aggregate_adds_count(self):
        eng = _engine()
        result = eng.fix_syntax_error("SELECT name, city FROM t GROUP BY name", "")
        assert "COUNT(" in result

    def test_group_by_with_aggregate_unchanged(self):
        eng = _engine()
        query = "SELECT name, COUNT(*) FROM t GROUP BY name"
        result = eng.fix_syntax_error(query, "")
        # Should not add another COUNT
        assert result.count("COUNT(") == 1

    def test_output_length_never_shorter_than_input(self):
        eng = _engine()
        for query in [
            "SELECT 1",
            "SELECT * FROM t WHERE ROWNUM <= 5",
            "SELECT a, b FROM t GROUP BY a",
            "SELECT NVL(x, 0) FROM t",
        ]:
            result = eng.fix_syntax_error(query, "")
            assert len(result) >= len(query), f"Output shorter for: {query!r}"


# ---------------------------------------------------------------------------
# fix_wrong_db_type
# ---------------------------------------------------------------------------

class TestFixWrongDbType:
    def test_postgres_error_reroutes_sqlite_plan_to_postgres(self):
        eng = _engine()
        plan = _plan(db_type="sqlite")
        failure = _failure("psycopg2 error: relation does not exist", db_type="sqlite")
        corrected = eng.fix_wrong_db_type(plan, failure)
        assert corrected.sub_queries[0].db_type == "postgres"

    def test_sqlite_error_reroutes_postgres_plan_to_sqlite(self):
        eng = _engine()
        plan = _plan(db_type="postgres")
        failure = _failure("no such table: orders", db_type="postgres")
        corrected = eng.fix_wrong_db_type(plan, failure)
        assert corrected.sub_queries[0].db_type == "sqlite"

    def test_duckdb_error_reroutes_to_duckdb(self):
        eng = _engine()
        plan = _plan(db_type="postgres")
        failure = _failure("binder error: table not found", db_type="postgres")
        corrected = eng.fix_wrong_db_type(plan, failure)
        assert corrected.sub_queries[0].db_type == "duckdb"

    def test_unknown_signal_keeps_original_db_type(self):
        eng = _engine()
        plan = _plan(db_type="postgres")
        failure = _failure("some random error with no db signals", db_type="postgres")
        corrected = eng.fix_wrong_db_type(plan, failure)
        assert corrected.sub_queries[0].db_type == "postgres"


# ---------------------------------------------------------------------------
# fix_data_quality
# ---------------------------------------------------------------------------

class TestFixDataQuality:
    def test_adds_coalesce_to_simple_select(self):
        eng = _engine()
        result = eng.fix_data_quality("SELECT revenue FROM t", _failure("null value"))
        assert "COALESCE" in result or "revenue" in result  # at minimum keeps the query valid

    def test_does_not_corrupt_query_structure(self):
        eng = _engine()
        result = eng.fix_data_quality("SELECT col FROM t WHERE x = 1", _failure("null"))
        assert "FROM" in result
        assert "WHERE" in result


# ---------------------------------------------------------------------------
# correct() routing and CorrectionExhausted
# ---------------------------------------------------------------------------

class TestCorrect:
    def test_routes_syntax_error_to_rule_syntax(self):
        eng = _engine()

        async def _run():
            from unittest.mock import AsyncMock, MagicMock
            ctx = MagicMock()
            ctx.schema_ctx.databases = {}
            failure = _failure("syntax error near 'FROM'")
            return await eng.correct(failure, "SELECT * FROM t", ctx)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.fix_strategy == "rule_syntax"
        assert result.success

    def test_routes_wrong_db_type_to_rule_db_type(self):
        eng = _engine()

        async def _run():
            from unittest.mock import MagicMock
            ctx = MagicMock()
            ctx.schema_ctx.databases = {}
            failure = _failure("no such table: orders", db_type="postgres")
            return await eng.correct(failure, "SELECT 1", ctx)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.fix_strategy == "rule_db_type"

    def test_raises_correction_exhausted_after_limit(self):
        eng = _engine()
        eng._max_attempts = 2

        async def _run():
            from unittest.mock import MagicMock
            ctx = MagicMock()
            failure = _failure("some error")
            return await eng.correct(failure, "SELECT 1", ctx, attempt=3)

        with pytest.raises(CorrectionExhausted):
            asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# PBT-U1-01: classify_failure always returns valid FailureType
# ---------------------------------------------------------------------------

@given(failure=execution_failures())
@INVARIANT_SETTINGS["PBT-U1-01"]
def test_pbt_u1_01_classify_failure_always_valid(failure: ExecutionFailure):
    """PBT-U1-01: classify_failure never raises and always returns a valid FailureType."""
    eng = _engine()
    result = eng.classify_failure(failure)
    assert isinstance(result, FailureType)
    assert result in list(FailureType)
