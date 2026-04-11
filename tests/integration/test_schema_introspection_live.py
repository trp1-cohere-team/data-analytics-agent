"""Integration tests for schema introspection against a live MCP Toolbox.

REQUIRES: MCP Toolbox running at settings.mcp_toolbox_url (default: http://localhost:5000).

Run with:
    pytest tests/integration/ -m integration

Skip automatically if MCP Toolbox is not reachable.
"""
from __future__ import annotations

import asyncio
import socket

import pytest

from agent.config import settings
from agent.models import DBSchema, SchemaContext
from utils.schema_introspector import AiohttpMCPClient, introspect_all


# ---------------------------------------------------------------------------
# Skip guard — skip entire module if MCP Toolbox unreachable
# ---------------------------------------------------------------------------

def _mcp_reachable(url: str) -> bool:
    """Quick TCP probe to check if MCP Toolbox is listening."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5000
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.integration

_mcp_available = _mcp_reachable(settings.mcp_toolbox_url)


# ---------------------------------------------------------------------------
# Live introspection tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _mcp_available, reason="MCP Toolbox not reachable")
class TestSchemaIntrospectionLive:
    @pytest.fixture(scope="class")
    def schema_ctx(self) -> SchemaContext:
        """Run introspect_all once and share result across the class."""
        client = AiohttpMCPClient(settings.mcp_toolbox_url)
        return asyncio.run(introspect_all(client=client))

    def test_returns_schema_context(self, schema_ctx: SchemaContext):
        assert isinstance(schema_ctx, SchemaContext)

    def test_four_databases_present(self, schema_ctx: SchemaContext):
        assert len(schema_ctx.databases) == 4

    def test_all_values_are_db_schema(self, schema_ctx: SchemaContext):
        for db_name, db in schema_ctx.databases.items():
            assert isinstance(db, DBSchema), f"Expected DBSchema for {db_name}"

    def test_at_least_one_db_succeeded(self, schema_ctx: SchemaContext):
        ok_count = sum(1 for db in schema_ctx.databases.values() if db.error is None)
        assert ok_count >= 1, "All databases failed introspection"

    def test_no_unresolved_error_object_leaks(self, schema_ctx: SchemaContext):
        """error field is str or None, not an Exception instance."""
        for db in schema_ctx.databases.values():
            assert db.error is None or isinstance(db.error, str)

    def test_partial_failure_does_not_block(self, schema_ctx: SchemaContext):
        """Even if some DBs fail, introspect_all returns a complete SchemaContext."""
        assert schema_ctx is not None

    def test_failed_db_has_empty_tables(self, schema_ctx: SchemaContext):
        for db in schema_ctx.databases.values():
            if db.error is not None:
                assert db.tables == [], f"Failed DB {db.db_name} should have empty tables"

    def test_successful_db_has_tables(self, schema_ctx: SchemaContext):
        for db in schema_ctx.databases.values():
            if db.error is None:
                # A connected DB should expose at least one table
                assert len(db.tables) >= 1, f"Connected DB {db.db_name} has no tables"

    def test_db_types_correct(self, schema_ctx: SchemaContext):
        expected_types = {"postgres", "sqlite", "mongodb", "duckdb"}
        actual_types = {db.db_type for db in schema_ctx.databases.values()}
        assert actual_types == expected_types

    def test_columns_populated_in_successful_dbs(self, schema_ctx: SchemaContext):
        for db in schema_ctx.databases.values():
            if db.error is None:
                for tbl in db.tables:
                    assert len(tbl.columns) >= 1, (
                        f"Table {tbl.name} in {db.db_name} has no columns"
                    )


# ---------------------------------------------------------------------------
# Timeout resilience test (mocked partial failure)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _mcp_available, reason="MCP Toolbox not reachable")
@pytest.mark.asyncio
async def test_outer_timeout_does_not_crash():
    """introspect_all completes (possibly partial) within outer ceiling."""
    # Use a very short outer timeout to simulate ceiling hit; should not raise
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "outer_introspect_timeout", 0.01)
        # May return partial or all-error schema — must not raise
        result = await introspect_all()
    assert isinstance(result, SchemaContext)
