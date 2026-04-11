"""Multi-DB Execution Engine for The Oracle Forge agent.

Implements the full 6-step execution pipeline:
  1. JoinKeyResolver.pre_execute_resolve — SQL query rewrite for join key format mismatch
  2. asyncio.gather fan-out — parallel sub-query execution
  3. Result classification — wrap exceptions as SubQueryResult failures
  4. JoinKeyResolver.post_result_resolve — MongoDB join key transform on result rows
  5. ResultMerger.merge — UNION / LEFT_JOIN / FIRST_ONLY + stage-2 row cap
  6. ExecutionResult assembly — results + merged_rows + failures

Design decisions:
  - Q1=D: UNION + LEFT_JOIN + FIRST_ONLY merge strategies
  - Q2=B: partial failure continuation (failed sub-queries don't abort the plan)
  - Q3=C: JoinKeyResolver pre-exec (SQL) + post-result (MongoDB)
  - Q4=A: MongoDB pipeline passed through unchanged from LLM
  - NFR Q1=B: EagerConnectionGuard — health check in __aenter__
  - NFR Q2=C: DoubleRowCapGuard — per-connector cap + post-merge cap
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from agent.config import settings
from agent.execution.mcp_client import AiohttpMCPClient, MCPClient, _classify_error, probe_mcp_toolbox
from agent.models import (
    ExecutionFailure,
    ExecutionResult,
    MergeSpec,
    QueryPlan,
    SubQuery,
    SubQueryResult,
)
from utils.join_key_utils import build_transform_expression, detect_format, transform_key

logger = logging.getLogger("agent.execution")

_SUB_QUERY_TIMEOUT_S = 30.0  # EE-02: 30s per sub-query


# ---------------------------------------------------------------------------
# ObservabilityEmitter — structured logging (never logs row content)
# ---------------------------------------------------------------------------

class _ObservabilityEmitter:
    """Thin wrapper for structured execution logs.

    SEC-U2-03 / SEC-U2-04: row content is NEVER logged — only counts, IDs,
    types, and timings.
    """

    def emit_complete(self, result: SubQueryResult) -> None:
        logger.info(
            "sub_query_complete",
            extra={
                "sub_query_id": result.sub_query_id,
                "db_type": result.db_type,
                "row_count": result.row_count,
                "execution_time_ms": result.execution_time_ms,
                "row_cap_applied": result.row_cap_applied,
            },
        )

    def emit_failure(self, result: SubQueryResult, failure: ExecutionFailure) -> None:
        logger.warning(
            "sub_query_failed",
            extra={
                "sub_query_id": result.sub_query_id,
                "db_type": result.db_type,
                "error_type": failure.error_type,
                "error_message": (result.error or "")[:200],
            },
        )

    def emit_join_rewrite(self, sq: SubQuery) -> None:
        logger.debug(
            "join_key_rewritten",
            extra={
                "sub_query_id": sq.id,
                "db_type": sq.db_type,
                "join_key": sq.join_key,
            },
        )

    def emit_row_cap(self, sq_id: str, original_count: int, capped_at: int) -> None:
        logger.warning(
            "row_cap_applied",
            extra={
                "sub_query_id": sq_id,
                "original_count": original_count,
                "capped_at": capped_at,
            },
        )


_emitter = _ObservabilityEmitter()


# ---------------------------------------------------------------------------
# RowCapGuard — two-stage row capping
# ---------------------------------------------------------------------------

def _apply_per_subquery_cap(
    rows: list[dict[str, Any]], cap: int
) -> tuple[list[dict[str, Any]], bool]:
    """Stage-1 cap: truncate rows returned by a single connector.

    Returns (possibly_truncated_rows, row_cap_applied).
    Bounds memory during asyncio.gather to N × MAX_RESULT_ROWS.
    """
    if len(rows) > cap:
        return rows[:cap], True
    return rows, False


def _apply_merge_cap(
    merged: list[dict[str, Any]], cap: int
) -> tuple[list[dict[str, Any]], bool]:
    """Stage-2 cap: truncate merged result before returning to Orchestrator.

    Returns (possibly_truncated_merged, merge_row_cap_applied).
    Bounds LLM context window exposure (critical for UNION of N full results).
    """
    if len(merged) > cap:
        return merged[:cap], True
    return merged, False


# ---------------------------------------------------------------------------
# DB Connectors — one per supported DB type
# ---------------------------------------------------------------------------

class _BaseConnector:
    """Common logic shared by all DB connectors."""

    def __init__(self, mcp_client: MCPClient, max_rows: int) -> None:
        self._client = mcp_client
        self._max_rows = max_rows

    def _cap_rows(
        self, rows: list[dict[str, Any]], sq_id: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows, capped = _apply_per_subquery_cap(rows, self._max_rows)
        if capped:
            _emitter.emit_row_cap(sq_id, len(rows) + (len(rows) - len(rows)), self._max_rows)
        return rows, capped


class _PostgreSQLConnector(_BaseConnector):
    async def execute(self, sq: SubQuery) -> tuple[list[dict[str, Any]], bool]:
        result = await self._client.call_tool("postgres_query", {"query": sq.query})
        rows = result.get("result", [])
        return self._cap_rows(rows, sq.id)


class _SQLiteConnector(_BaseConnector):
    async def execute(self, sq: SubQuery) -> tuple[list[dict[str, Any]], bool]:
        result = await self._client.call_tool("sqlite_query", {"query": sq.query})
        rows = result.get("result", [])
        return self._cap_rows(rows, sq.id)


class _MongoDBConnector(_BaseConnector):
    async def execute(self, sq: SubQuery) -> tuple[list[dict[str, Any]], bool]:
        # Q4=A: pipeline is pre-built by LLM — pass through unchanged
        result = await self._client.call_tool(
            "mongodb_aggregate",
            {"pipeline": sq.pipeline, "collection": sq.collection},
        )
        rows = result.get("result", [])
        return self._cap_rows(rows, sq.id)


class _DuckDBConnector(_BaseConnector):
    async def execute(self, sq: SubQuery) -> tuple[list[dict[str, Any]], bool]:
        result = await self._client.call_tool("duckdb_query", {"query": sq.query})
        rows = result.get("result", [])
        return self._cap_rows(rows, sq.id)


# ---------------------------------------------------------------------------
# QueryRouter — dispatches SubQuery to the correct connector
# ---------------------------------------------------------------------------

class _QueryRouter:
    """Maps db_type strings to connector instances."""

    def __init__(self, mcp_client: MCPClient, max_rows: int) -> None:
        self._connectors: dict[str, _BaseConnector] = {
            "postgres": _PostgreSQLConnector(mcp_client, max_rows),
            "sqlite": _SQLiteConnector(mcp_client, max_rows),
            "mongodb": _MongoDBConnector(mcp_client, max_rows),
            "duckdb": _DuckDBConnector(mcp_client, max_rows),
        }

    def get_connector(self, db_type: str) -> _BaseConnector:
        connector = self._connectors.get(db_type)
        if connector is None:
            raise ValueError(f"Unknown db_type: {db_type!r}")
        return connector


# ---------------------------------------------------------------------------
# JoinKeyResolver — pre-exec SQL rewrite + post-result MongoDB transform
# ---------------------------------------------------------------------------

class _JoinKeyResolver:
    """Resolves join key format mismatches across DB sub-queries.

    Stateless — all decisions computed from SubQuery fields and live row data.
    Delegates to U5 utils: detect_format, build_transform_expression, transform_key.
    """

    def pre_execute_resolve(self, plan: QueryPlan) -> None:
        """Rewrite SQL sub-query join key columns to match target format.

        Only applies to SQL-based DBs (postgres, sqlite, duckdb).
        MongoDB is handled post-result (Q3=C).
        Mutates SubQuery.query in-place; never raises.
        """
        sql_types = {"postgres", "sqlite", "duckdb"}
        for sq in plan.sub_queries:
            if sq.db_type not in sql_types:
                continue
            if sq.join_key is None:
                continue
            src_fmt = sq.source_join_format
            tgt_fmt = sq.target_join_format
            if src_fmt is None or tgt_fmt is None or src_fmt == tgt_fmt:
                continue
            expr = build_transform_expression(
                sq.join_key,
                src_fmt,
                tgt_fmt,
                sq.db_type,
                prefix=sq.join_key_prefix,
                width=sq.join_key_width,
            )
            if expr is not None:
                sq.query = sq.query.replace(sq.join_key, expr, 1)
                _emitter.emit_join_rewrite(sq)
            else:
                sq.join_key_unresolvable = True
                logger.warning(
                    "join_key_unresolvable",
                    extra={"sub_query_id": sq.id, "db_type": sq.db_type},
                )

    def post_result_resolve(
        self, results: list[SubQueryResult], plan: QueryPlan
    ) -> None:
        """Transform join key values in MongoDB result rows to match target format.

        Applies detect_format on live result rows; transforms in-place.
        Never raises (transform failures leave value unchanged).
        """
        sq_map = {sq.id: sq for sq in plan.sub_queries}
        for result in results:
            if result.error is not None:
                continue
            sq = sq_map.get(result.sub_query_id)
            if sq is None or sq.db_type != "mongodb" or sq.join_key is None:
                continue
            key_values = [
                row[sq.join_key]
                for row in result.rows
                if sq.join_key in row
            ]
            if not key_values:
                continue
            actual_fmt = detect_format(key_values).primary_format
            tgt_fmt = sq.target_join_format
            if tgt_fmt is None or actual_fmt == tgt_fmt:
                continue
            for row in result.rows:
                if sq.join_key not in row:
                    continue
                transformed = transform_key(
                    row[sq.join_key],
                    actual_fmt,
                    tgt_fmt,
                    prefix=sq.join_key_prefix,
                    width=sq.join_key_width,
                )
                if transformed is not None:
                    row[sq.join_key] = transformed
                # else: leave unchanged (unsupported pair — log omitted, not an error)


# ---------------------------------------------------------------------------
# ResultMerger — UNION / LEFT_JOIN / FIRST_ONLY + stage-2 cap
# ---------------------------------------------------------------------------

class _ResultMerger:
    """Merges sub-query results according to MergeSpec strategy.

    Stage-2 RowCapGuard fires after merge (bounds Orchestrator input).
    """

    def __init__(self, max_rows: int) -> None:
        self._max_rows = max_rows

    def merge(
        self,
        results: list[SubQueryResult],
        spec: MergeSpec,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return (merged_rows, merge_row_cap_applied)."""
        strategy = (spec.strategy or "UNION").upper()
        if strategy == "UNION":
            merged = self._union(results)
        elif strategy == "LEFT_JOIN":
            merged = self._left_join(results, spec)
        elif strategy == "FIRST_ONLY":
            merged = self._first_only(results)
            # FIRST_ONLY is already bounded by stage-1 cap — no stage-2 needed
            return merged, False
        else:
            logger.warning("unknown_merge_strategy", extra={"strategy": strategy})
            merged = self._union(results)

        merged, capped = _apply_merge_cap(merged, self._max_rows)
        if capped:
            logger.warning(
                "merge_row_cap_applied",
                extra={"original_count": len(merged), "capped_at": self._max_rows},
            )
        return merged, capped

    def _union(self, results: list[SubQueryResult]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for r in results:
            if r.is_success:
                merged.extend(r.rows)
        return merged

    def _left_join(
        self, results: list[SubQueryResult], spec: MergeSpec
    ) -> list[dict[str, Any]]:
        join_key = spec.join_key
        left_db_type = spec.left_db_type

        # Identify left result
        left_result: SubQueryResult | None = None
        right_results: list[SubQueryResult] = []
        for r in results:
            if r.is_success and r.db_type == left_db_type and left_result is None:
                left_result = r
            elif r.is_success and r.db_type != left_db_type:
                right_results.append(r)

        if left_result is None:
            return []

        # Index right rows by join key value
        right_by_key: dict[Any, list[dict[str, Any]]] = {}
        for r in right_results:
            for row in r.rows:
                key_val = row.get(join_key)
                right_by_key.setdefault(key_val, []).append(row)

        # Left join — unmatched left rows get empty {} fill
        merged: list[dict[str, Any]] = []
        for left_row in left_result.rows:
            key_val = left_row.get(join_key)
            right_matches = right_by_key.get(key_val, [{}])
            for right_row in right_matches:
                merged.append({**left_row, **right_row})  # right overwrites on collision
        return merged

    def _first_only(self, results: list[SubQueryResult]) -> list[dict[str, Any]]:
        for r in results:
            if r.is_success and r.rows:
                return list(r.rows)
        return []


# ---------------------------------------------------------------------------
# MultiDBEngine — top-level async context manager
# ---------------------------------------------------------------------------

class MultiDBEngine:
    """Async context manager that executes QueryPlans across multiple databases.

    Usage:
        async with MultiDBEngine(mcp_toolbox_url) as engine:
            result = await engine.execute_plan(plan)

    EagerConnectionGuard: __aenter__ probes MCP Toolbox /healthz and raises
    RuntimeError immediately if unreachable — preventing silent per-query failures.

    SEC-U2-01: mcp_toolbox_url always sourced from config/caller — never hardcoded.
    RES-U2-01: one aiohttp.ClientSession per MultiDBEngine instance (created in __aenter__).
    """

    def __init__(
        self,
        mcp_toolbox_url: str | None = None,
        max_result_rows: int | None = None,
    ) -> None:
        self._mcp_url = (mcp_toolbox_url or settings.mcp_toolbox_url).rstrip("/")
        self._max_rows = max_result_rows if max_result_rows is not None else settings.max_result_rows
        self._session: aiohttp.ClientSession | None = None
        self._mcp_client: AiohttpMCPClient | None = None
        self._router: _QueryRouter | None = None
        self._merger = _ResultMerger(self._max_rows)
        self._join_resolver = _JoinKeyResolver()

    async def __aenter__(self) -> "MultiDBEngine":
        self._session = aiohttp.ClientSession()
        # EagerConnectionGuard: probe before allowing execute_plan
        await probe_mcp_toolbox(self._session, self._mcp_url)
        self._mcp_client = AiohttpMCPClient(self._session, self._mcp_url)
        self._router = _QueryRouter(self._mcp_client, self._max_rows)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._mcp_client = None
        self._router = None

    async def execute_plan(self, plan: QueryPlan) -> ExecutionResult:
        """Execute a QueryPlan and return a merged ExecutionResult.

        Always returns ExecutionResult — never raises (partial failure model).
        Must be called inside an `async with MultiDBEngine(...)` block.
        """
        if self._router is None:
            raise RuntimeError(
                "execute_plan called outside of 'async with MultiDBEngine()' block"
            )

        # Step 1: Pre-execution join key resolve (SQL DBs only)
        self._join_resolver.pre_execute_resolve(plan)

        # Step 2: Fan-out execution
        raw_results = await asyncio.gather(
            *[self._execute_sub_query(sq) for sq in plan.sub_queries],
            return_exceptions=True,
        )

        # Step 3: Classify results — wrap exceptions as failures
        sub_results: list[SubQueryResult] = []
        for sq, raw in zip(plan.sub_queries, raw_results):
            if isinstance(raw, BaseException):
                sub_results.append(
                    SubQueryResult(
                        sub_query_id=sq.id,
                        db_type=sq.db_type,
                        rows=[],
                        row_count=0,
                        error=str(raw),
                        row_cap_applied=False,
                    )
                )
            else:
                sub_results.append(raw)

        # Step 4: Post-result join key resolve (MongoDB only)
        self._join_resolver.post_result_resolve(sub_results, plan)

        # Step 5: Merge
        merged_rows, merge_row_cap_applied = self._merger.merge(
            sub_results, plan.merge_spec
        )

        # Step 6: Assemble ExecutionResult
        failures = self._build_failures(sub_results)

        return ExecutionResult(
            results=sub_results,
            merged_rows=merged_rows,
            failures=failures,
            merge_row_cap_applied=merge_row_cap_applied,
        )

    async def _execute_sub_query(self, sq: SubQuery) -> SubQueryResult:
        """Execute one sub-query with a 30s timeout; return SubQueryResult.

        EE-03: all exceptions wrapped — none propagate to asyncio.gather.
        """
        assert self._router is not None  # always true inside execute_plan
        start = time.monotonic()
        try:
            connector = self._router.get_connector(sq.db_type)
            rows, row_cap_applied = await asyncio.wait_for(
                connector.execute(sq),
                timeout=_SUB_QUERY_TIMEOUT_S,
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            result = SubQueryResult(
                sub_query_id=sq.id,
                db_type=sq.db_type,
                rows=rows,
                row_count=len(rows),
                execution_time_ms=elapsed_ms,
                error=None,
                row_cap_applied=row_cap_applied,
            )
            _emitter.emit_complete(result)
            return result

        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000
            result = SubQueryResult(
                sub_query_id=sq.id,
                db_type=sq.db_type,
                rows=[],
                row_count=0,
                execution_time_ms=elapsed_ms,
                error=f"sub_query_timeout_{int(_SUB_QUERY_TIMEOUT_S)}s",
                row_cap_applied=False,
            )
            failure = ExecutionFailure(
                sub_query_id=sq.id,
                db_type=sq.db_type,
                error_message=result.error or "",
                error_type="timeout",
            )
            _emitter.emit_failure(result, failure)
            return result

        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.monotonic() - start) * 1000
            error_type = _classify_error(exc, None, "")
            error_msg = str(exc)
            result = SubQueryResult(
                sub_query_id=sq.id,
                db_type=sq.db_type,
                rows=[],
                row_count=0,
                execution_time_ms=elapsed_ms,
                error=error_msg,
                row_cap_applied=False,
            )
            failure = ExecutionFailure(
                sub_query_id=sq.id,
                db_type=sq.db_type,
                error_message=error_msg[:500],
                error_type=error_type,
            )
            _emitter.emit_failure(result, failure)
            return result

    @staticmethod
    def _build_failures(results: list[SubQueryResult]) -> list[ExecutionFailure]:
        """Build the failures list from failed SubQueryResults."""
        failures: list[ExecutionFailure] = []
        for r in results:
            if not r.is_success:
                failures.append(
                    ExecutionFailure(
                        sub_query_id=r.sub_query_id,
                        db_type=r.db_type,
                        error_message=(r.error or "")[:500],
                        error_type=_classify_error(None, None, r.error or ""),
                    )
                )
        return failures
