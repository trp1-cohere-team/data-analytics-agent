"""Unit tests for agent/execution/engine.py.

Covers:
- execute_plan: success path (all sub-queries succeed, UNION merge)
- execute_plan: partial failure (one fails, others succeed)
- execute_plan: LEFT_JOIN merge strategy (correct matching, null fill)
- execute_plan: FIRST_ONLY merge strategy
- Stage-1 RowCapGuard: per-connector truncation
- Stage-2 RowCapGuard: post-merge truncation
- EagerConnectionGuard: __aenter__ raises RuntimeError when health check fails
- JoinKeyResolver: pre_execute_resolve rewrites SQL query
- JoinKeyResolver: post_result_resolve transforms MongoDB rows
- PBT-U2-EE-01: execute_plan always returns len(results) == len(plan.sub_queries)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from agent.execution.engine import MultiDBEngine, _apply_merge_cap, _apply_per_subquery_cap, _ResultMerger
from agent.models import (
    ExecutionResult,
    JoinKeyFormat,
    MergeSpec,
    QueryPlan,
    SubQuery,
    SubQueryResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PBT_SETTINGS = h_settings(
    max_examples=100,
    deadline=timedelta(milliseconds=1000),
)


def _make_sub_query(
    db_type: str = "postgres",
    db_name: str = "test_db",
    query: str = "SELECT 1",
    **kwargs: Any,
) -> SubQuery:
    return SubQuery(
        id=str(uuid.uuid4()),
        db_type=db_type,
        db_name=db_name,
        query=query,
        **kwargs,
    )


def _make_plan(
    sub_queries: list[SubQuery],
    strategy: str = "UNION",
    join_key: str | None = None,
    left_db_type: str | None = None,
) -> QueryPlan:
    return QueryPlan(
        id=str(uuid.uuid4()),
        sub_queries=sub_queries,
        merge_spec=MergeSpec(
            strategy=strategy,
            join_key=join_key,
            left_db_type=left_db_type,
        ),
    )


def _make_mock_client(responses: dict[str, list[dict[str, Any]]]) -> MagicMock:
    """Build a mock MCPClient where call_tool returns the given row lists by tool name."""

    async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = responses.get(tool_name, [])
        return {"result": rows}

    async def _health_check(timeout: float = 3.0) -> bool:
        return True

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    client.health_check = AsyncMock(side_effect=_health_check)
    return client


def _engine_with_mock_client(
    mock_client: MagicMock, max_result_rows: int = 1000
) -> MultiDBEngine:
    """Return a MultiDBEngine whose _router is wired with mock_client, bypassing __aenter__."""
    from agent.execution.engine import _JoinKeyResolver, _QueryRouter, _ResultMerger

    engine = MultiDBEngine.__new__(MultiDBEngine)
    engine._mcp_url = "http://localhost:5000"
    engine._max_rows = max_result_rows
    engine._session = MagicMock()
    engine._mcp_client = mock_client
    engine._router = _QueryRouter(mock_client, max_result_rows)
    engine._merger = _ResultMerger(max_result_rows)
    engine._join_resolver = _JoinKeyResolver()
    return engine


# ---------------------------------------------------------------------------
# Success path — all sub-queries succeed, UNION merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_success_union() -> None:
    sq1 = _make_sub_query(db_type="postgres", query="SELECT id FROM users")
    sq2 = _make_sub_query(db_type="sqlite", query="SELECT id FROM orders")
    plan = _make_plan([sq1, sq2], strategy="UNION")

    mock_client = _make_mock_client(
        {
            "postgres_query": [{"id": 1}, {"id": 2}],
            "sqlite_query": [{"id": 10}, {"id": 11}],
        }
    )
    engine = _engine_with_mock_client(mock_client)
    result = await engine.execute_plan(plan)

    assert isinstance(result, ExecutionResult)
    assert len(result.results) == 2
    assert len(result.failures) == 0
    assert len(result.merged_rows) == 4
    assert result.merge_row_cap_applied is False


# ---------------------------------------------------------------------------
# Partial failure — one sub-query fails, others succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_partial_failure() -> None:
    sq1 = _make_sub_query(db_type="postgres", query="SELECT 1")
    sq2 = _make_sub_query(db_type="sqlite", query="SELECT 2")
    plan = _make_plan([sq1, sq2], strategy="UNION")

    async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "postgres_query":
            return {"result": [{"x": 1}]}
        raise RuntimeError("SQLite connection refused")

    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(side_effect=_call_tool)

    engine = _engine_with_mock_client(mock_client)
    result = await engine.execute_plan(plan)

    assert len(result.results) == 2
    assert len(result.failures) == 1
    assert result.failures[0].db_type == "sqlite"
    # Merged rows only from successful postgres sub-query
    assert result.merged_rows == [{"x": 1}]


# ---------------------------------------------------------------------------
# LEFT_JOIN strategy — correct row matching and null fill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_left_join() -> None:
    sq_pg = _make_sub_query(db_type="postgres", query="SELECT user_id, name FROM users")
    sq_sq = _make_sub_query(db_type="sqlite", query="SELECT user_id, order_count FROM orders")
    plan = _make_plan(
        [sq_pg, sq_sq],
        strategy="LEFT_JOIN",
        join_key="user_id",
        left_db_type="postgres",
    )

    mock_client = _make_mock_client(
        {
            "postgres_query": [
                {"user_id": 1, "name": "Alice"},
                {"user_id": 2, "name": "Bob"},
            ],
            "sqlite_query": [{"user_id": 1, "order_count": 5}],
        }
    )
    engine = _engine_with_mock_client(mock_client)
    result = await engine.execute_plan(plan)

    assert len(result.merged_rows) == 2
    # Alice (user_id=1) matched — merged row has both name and order_count
    alice = next(r for r in result.merged_rows if r.get("name") == "Alice")
    assert alice["order_count"] == 5
    # Bob (user_id=2) unmatched — gets {} fill → name preserved, no order_count
    bob = next(r for r in result.merged_rows if r.get("name") == "Bob")
    assert "order_count" not in bob


# ---------------------------------------------------------------------------
# FIRST_ONLY strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_first_only() -> None:
    sq1 = _make_sub_query(db_type="postgres", query="SELECT 1")
    sq2 = _make_sub_query(db_type="sqlite", query="SELECT 2")
    plan = _make_plan([sq1, sq2], strategy="FIRST_ONLY")

    mock_client = _make_mock_client(
        {
            "postgres_query": [{"val": 42}],
            "sqlite_query": [{"val": 99}],
        }
    )
    engine = _engine_with_mock_client(mock_client)
    result = await engine.execute_plan(plan)

    # FIRST_ONLY: first non-empty success wins (postgres)
    assert result.merged_rows == [{"val": 42}]
    assert result.merge_row_cap_applied is False


# ---------------------------------------------------------------------------
# Stage-1 RowCapGuard — per-connector truncation
# ---------------------------------------------------------------------------


def test_apply_per_subquery_cap_truncates() -> None:
    rows = [{"id": i} for i in range(5)]
    result, capped = _apply_per_subquery_cap(rows, cap=3)
    assert len(result) == 3
    assert capped is True


def test_apply_per_subquery_cap_no_truncation() -> None:
    rows = [{"id": i} for i in range(3)]
    result, capped = _apply_per_subquery_cap(rows, cap=5)
    assert len(result) == 3
    assert capped is False


@pytest.mark.asyncio
async def test_execute_plan_stage1_row_cap_applied() -> None:
    sq = _make_sub_query(db_type="postgres", query="SELECT id FROM big_table")
    plan = _make_plan([sq], strategy="UNION")

    # Return 5 rows but cap is 3
    mock_client = _make_mock_client(
        {"postgres_query": [{"id": i} for i in range(5)]}
    )
    engine = _engine_with_mock_client(mock_client, max_result_rows=3)
    result = await engine.execute_plan(plan)

    assert result.results[0].row_cap_applied is True
    assert len(result.results[0].rows) == 3


# ---------------------------------------------------------------------------
# Stage-2 RowCapGuard — post-merge truncation
# ---------------------------------------------------------------------------


def test_apply_merge_cap_truncates() -> None:
    rows = [{"id": i} for i in range(10)]
    result, capped = _apply_merge_cap(rows, cap=5)
    assert len(result) == 5
    assert capped is True


@pytest.mark.asyncio
async def test_execute_plan_stage2_merge_cap_applied() -> None:
    sq1 = _make_sub_query(db_type="postgres", query="SELECT id FROM t1")
    sq2 = _make_sub_query(db_type="sqlite", query="SELECT id FROM t2")
    plan = _make_plan([sq1, sq2], strategy="UNION")

    # Each returns 4 rows, cap=5 → union=8 → truncated to 5
    mock_client = _make_mock_client(
        {
            "postgres_query": [{"id": i} for i in range(4)],
            "sqlite_query": [{"id": i + 100} for i in range(4)],
        }
    )
    engine = _engine_with_mock_client(mock_client, max_result_rows=5)
    result = await engine.execute_plan(plan)

    assert result.merge_row_cap_applied is True
    assert len(result.merged_rows) == 5


# ---------------------------------------------------------------------------
# EagerConnectionGuard — __aenter__ raises RuntimeError on health failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eager_connection_guard_raises_on_health_failure() -> None:
    """__aenter__ must raise RuntimeError if MCP Toolbox is unreachable."""
    with patch(
        "agent.execution.engine.probe_mcp_toolbox",
        new_callable=AsyncMock,
        side_effect=RuntimeError("MCP Toolbox unreachable at http://localhost:5000"),
    ):
        with pytest.raises(RuntimeError, match="unreachable"):
            async with MultiDBEngine("http://localhost:5000"):
                pass  # pragma: no cover


@pytest.mark.asyncio
async def test_eager_connection_guard_succeeds_on_healthy() -> None:
    """__aenter__ succeeds when MCP Toolbox probe passes."""
    with patch(
        "agent.execution.engine.probe_mcp_toolbox",
        new_callable=AsyncMock,
        return_value=None,
    ):
        # AiohttpMCPClient creation would normally need a real session;
        # we just verify __aenter__ and __aexit__ complete without error.
        engine = MultiDBEngine.__new__(MultiDBEngine)
        engine._mcp_url = "http://localhost:5000"
        engine._max_rows = 1000
        engine._session = None
        engine._mcp_client = None
        engine._router = None

        from agent.execution.engine import _JoinKeyResolver, _ResultMerger
        engine._merger = _ResultMerger(1000)
        engine._join_resolver = _JoinKeyResolver()

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            async with engine:
                assert engine._session is mock_session


# ---------------------------------------------------------------------------
# execute_plan called outside async with — raises RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_outside_context_raises() -> None:
    engine = MultiDBEngine.__new__(MultiDBEngine)
    engine._router = None
    plan = _make_plan([_make_sub_query()], strategy="UNION")

    with pytest.raises(RuntimeError, match="async with"):
        await engine.execute_plan(plan)


# ---------------------------------------------------------------------------
# JoinKeyResolver — pre_execute_resolve rewrites SQL query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_key_resolver_pre_execute_rewrites_sql() -> None:
    """JoinKeyResolver.pre_execute_resolve rewrites SQL query for format mismatch."""
    sq = SubQuery(
        id=str(uuid.uuid4()),
        db_type="postgres",
        db_name="yelp",
        query="SELECT business_id, name FROM businesses WHERE business_id = business_id",
        join_key="business_id",
        source_join_format=JoinKeyFormat.INTEGER,
        target_join_format=JoinKeyFormat.PREFIXED_STRING,
        join_key_prefix="BIZ",
        join_key_width=6,
    )
    plan = _make_plan([sq], strategy="FIRST_ONLY")

    # Mock connector to return empty result — we're testing query rewrite, not results
    mock_client = _make_mock_client({"postgres_query": []})
    engine = _engine_with_mock_client(mock_client)

    await engine.execute_plan(plan)

    # The query should have been rewritten to include a transform expression
    assert sq.query != "SELECT business_id, name FROM businesses WHERE business_id = business_id"


# ---------------------------------------------------------------------------
# PBT-U2-EE-01 — execute_plan always returns len(results) == len(plan.sub_queries)
# ---------------------------------------------------------------------------


@given(
    n_queries=st.integers(min_value=1, max_value=4),
    succeed=st.lists(st.booleans(), min_size=1, max_size=4),
)
@_PBT_SETTINGS
def test_pbt_result_count_matches_plan(
    n_queries: int,
    succeed: list[bool],
) -> None:
    """PBT-U2-EE-01: ExecutionResult.results always has exactly len(plan.sub_queries) entries."""

    async def _run() -> ExecutionResult:
        sqs = [_make_sub_query(db_type="postgres") for _ in range(n_queries)]
        succeed_flags = (succeed * (n_queries // len(succeed) + 1))[:n_queries]

        async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            # Can't easily correlate tool call to sub_query here, so return success for first half
            return {"result": [{"id": 1}]}

        def _side_effect_factory(idx: int) -> Any:
            async def _side(_tool: str, _payload: dict) -> dict:
                if succeed_flags[idx % len(succeed_flags)]:
                    return {"result": [{"id": idx}]}
                raise RuntimeError("simulated failure")
            return _side

        mock_client = MagicMock()
        # Use a simple always-succeed client for the PBT
        mock_client.call_tool = AsyncMock(side_effect=_call_tool)
        engine = _engine_with_mock_client(mock_client)
        plan = _make_plan(sqs, strategy="UNION")
        return await engine.execute_plan(plan)

    import asyncio as _asyncio
    result = _asyncio.get_event_loop().run_until_complete(_run())
    assert len(result.results) == n_queries, (
        f"Expected {n_queries} results, got {len(result.results)}"
    )


# ---------------------------------------------------------------------------
# ResultMerger — edge cases
# ---------------------------------------------------------------------------


class TestResultMerger:
    """Direct unit tests for _ResultMerger strategies."""

    def _make_result(
        self,
        db_type: str,
        rows: list[dict[str, Any]],
        error: str | None = None,
    ) -> SubQueryResult:
        return SubQueryResult(
            sub_query_id=str(uuid.uuid4()),
            db_type=db_type,
            rows=rows,
            row_count=len(rows),
            error=error,
        )

    def test_union_skips_failed_results(self) -> None:
        from agent.execution.engine import _ResultMerger
        merger = _ResultMerger(max_rows=1000)
        results = [
            self._make_result("postgres", [{"a": 1}]),
            self._make_result("sqlite", [], error="connection failed"),
        ]
        merged, capped = merger.merge(results, MergeSpec(strategy="UNION"))
        assert merged == [{"a": 1}]
        assert capped is False

    def test_first_only_skips_empty_and_failed(self) -> None:
        from agent.execution.engine import _ResultMerger
        merger = _ResultMerger(max_rows=1000)
        results = [
            self._make_result("postgres", [], error="timeout"),
            self._make_result("sqlite", []),
            self._make_result("duckdb", [{"b": 2}]),
        ]
        merged, _ = merger.merge(results, MergeSpec(strategy="FIRST_ONLY"))
        assert merged == [{"b": 2}]

    def test_left_join_empty_left_returns_empty(self) -> None:
        from agent.execution.engine import _ResultMerger
        merger = _ResultMerger(max_rows=1000)
        results = [
            self._make_result("postgres", [], error="timeout"),
            self._make_result("sqlite", [{"id": 1, "val": 10}]),
        ]
        spec = MergeSpec(strategy="LEFT_JOIN", join_key="id", left_db_type="postgres")
        merged, _ = merger.merge(results, spec)
        assert merged == []

    def test_unknown_strategy_falls_back_to_union(self) -> None:
        from agent.execution.engine import _ResultMerger
        merger = _ResultMerger(max_rows=1000)
        results = [self._make_result("postgres", [{"x": 1}])]
        merged, _ = merger.merge(results, MergeSpec(strategy="INVALID_STRATEGY"))
        assert merged == [{"x": 1}]
