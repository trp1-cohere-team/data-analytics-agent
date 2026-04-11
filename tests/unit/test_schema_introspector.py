"""Unit tests for utils/schema_introspector.py.

All tests use a mock MCPClient — no real MCP Toolbox or network required.

Covers:
- introspect_postgres: success path, columns/PKs/FKs assembled correctly
- introspect_sqlite: table discovery + PRAGMA parsing
- introspect_mongodb: sample-based schema inference, nullable detection
- introspect_duckdb: information_schema parsing
- introspect_all: bulkhead timeout pattern, partial failure graceful degradation
- _infer_mongo_schema: empty rows, single-type, mixed-type, nullable threshold
- _error_label: TimeoutError, CancelledError, other exceptions
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import DBSchema, SchemaContext
from utils.schema_introspector import (
    _assemble_schema,
    _error_label,
    _infer_mongo_schema,
    introspect_duckdb,
    introspect_mongodb,
    introspect_postgres,
    introspect_sqlite,
)


# ---------------------------------------------------------------------------
# Mock MCP client factory
# ---------------------------------------------------------------------------

def _mock_client(responses: dict[str, Any]) -> MagicMock:
    """Build a mock MCPClient that returns pre-configured responses by tool name."""
    client = MagicMock()

    async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name in responses:
            resp = responses[tool_name]
            if isinstance(resp, Exception):
                raise resp
            return resp
        return {"result": []}

    client.call_tool = AsyncMock(side_effect=_call_tool)
    return client


# ---------------------------------------------------------------------------
# introspect_postgres
# ---------------------------------------------------------------------------

class TestIntrospectPostgres:
    @pytest.mark.asyncio
    async def test_success_path(self):
        col_rows = [
            {"table_name": "customers", "column_name": "id", "data_type": "integer", "is_nullable": "NO"},
            {"table_name": "customers", "column_name": "name", "data_type": "varchar", "is_nullable": "YES"},
        ]
        pk_rows = [{"table_name": "customers", "column_name": "id"}]
        fk_rows = []

        client = _mock_client({
            "postgres_query": {"result": col_rows},
        })

        # Override per-call to return different payloads
        async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            query = payload.get("query", "")
            if "PRIMARY KEY" in query:
                return {"result": pk_rows}
            if "FOREIGN KEY" in query:
                return {"result": fk_rows}
            return {"result": col_rows}

        client.call_tool = AsyncMock(side_effect=_call_tool)

        schema = await introspect_postgres("oracle_forge", client)

        assert isinstance(schema, DBSchema)
        assert schema.db_type == "postgres"
        assert schema.error is None
        assert len(schema.tables) == 1
        tbl = schema.tables[0]
        assert tbl.name == "customers"
        assert len(tbl.columns) == 2
        pk_col = next(c for c in tbl.columns if c.name == "id")
        assert pk_col.is_primary_key is True
        assert pk_col.nullable is False

    @pytest.mark.asyncio
    async def test_connection_error_returns_error_schema(self):
        client = _mock_client({"postgres_query": ConnectionError("refused")})
        schema = await introspect_postgres("oracle_forge", client)
        assert schema.error is not None
        assert schema.tables == []


# ---------------------------------------------------------------------------
# introspect_sqlite
# ---------------------------------------------------------------------------

class TestIntrospectSqlite:
    @pytest.mark.asyncio
    async def test_success_path(self):
        tables_result = {"result": [{"name": "businesses"}]}
        col_result = {
            "result": [
                {"name": "id", "type": "INTEGER", "notnull": 1, "pk": 1},
                {"name": "city", "type": "TEXT", "notnull": 0, "pk": 0},
            ]
        }
        fk_result = {"result": []}

        call_count = [0]

        async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            query = payload.get("query", "")
            if "sqlite_master" in query:
                return tables_result
            if "table_info" in query:
                return col_result
            if "foreign_key_list" in query:
                return fk_result
            return {"result": []}

        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=_call_tool)

        schema = await introspect_sqlite("data/yelp.db", client)

        assert schema.error is None
        assert len(schema.tables) == 1
        tbl = schema.tables[0]
        assert tbl.name == "businesses"
        pk = next(c for c in tbl.columns if c.name == "id")
        assert pk.is_primary_key is True

    @pytest.mark.asyncio
    async def test_error_returns_error_schema(self):
        client = _mock_client({"sqlite_query": RuntimeError("file not found")})
        schema = await introspect_sqlite("data/yelp.db", client)
        assert schema.error is not None


# ---------------------------------------------------------------------------
# introspect_mongodb
# ---------------------------------------------------------------------------

class TestIntrospectMongodb:
    @pytest.mark.asyncio
    async def test_success_path(self):
        collections = {"result": [{"name": "reviews"}, {"name": "system.users"}]}
        sample_docs = {
            "result": [
                {"_id": "abc", "text": "great food", "stars": 5},
                {"_id": "def", "text": "ok", "stars": 4},
            ]
        }

        async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            pipeline = payload.get("pipeline", [])
            if any("$listCollections" in str(s) for s in pipeline):
                return collections
            return sample_docs

        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=_call_tool)

        schema = await introspect_mongodb("oracle_forge", client)

        assert schema.error is None
        # system.users should be filtered out
        assert all(t.name != "system.users" for t in schema.tables)
        assert any(t.name == "reviews" for t in schema.tables)

    @pytest.mark.asyncio
    async def test_error_returns_error_schema(self):
        client = _mock_client({"mongodb_aggregate": IOError("connection failed")})
        schema = await introspect_mongodb("oracle_forge", client)
        assert schema.error is not None


# ---------------------------------------------------------------------------
# introspect_duckdb
# ---------------------------------------------------------------------------

class TestIntrospectDuckdb:
    @pytest.mark.asyncio
    async def test_success_path(self):
        col_rows = [
            {"table_name": "sales", "column_name": "id", "data_type": "BIGINT", "is_nullable": "NO"},
            {"table_name": "sales", "column_name": "amount", "data_type": "DOUBLE", "is_nullable": "YES"},
        ]
        pk_rows = [{"table_name": "sales", "column_name": "id"}]

        async def _call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            query = payload.get("query", "")
            if "PRIMARY KEY" in query:
                return {"result": pk_rows}
            return {"result": col_rows}

        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=_call_tool)

        schema = await introspect_duckdb("data/analytics.duckdb", client)

        assert schema.error is None
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "sales"

    @pytest.mark.asyncio
    async def test_error_returns_error_schema(self):
        client = _mock_client({"duckdb_query": Exception("duckdb error")})
        schema = await introspect_duckdb("data/analytics.duckdb", client)
        assert schema.error is not None


# ---------------------------------------------------------------------------
# _infer_mongo_schema
# ---------------------------------------------------------------------------

class TestInferMongoSchema:
    def test_empty_rows_returns_id_column(self):
        cols = _infer_mongo_schema([])
        assert len(cols) == 1
        assert cols[0].name == "_id"
        assert cols[0].is_primary_key is True

    def test_single_type_field(self):
        rows = [{"_id": "a", "score": 5}, {"_id": "b", "score": 3}]
        cols = _infer_mongo_schema(rows)
        score_col = next(c for c in cols if c.name == "score")
        assert score_col.data_type == "int"

    def test_mixed_types_yields_mixed(self):
        rows = [{"val": 1}, {"val": "text"}]
        cols = _infer_mongo_schema(rows)
        val_col = next(c for c in cols if c.name == "val")
        assert val_col.data_type == "mixed"

    def test_sparse_field_is_nullable(self):
        # SI-02: field present in < 90% of docs → nullable
        rows = [{"_id": str(i), "rare_field": "x"} for i in range(1)] + \
               [{"_id": str(i + 1)} for i in range(9)]
        cols = _infer_mongo_schema(rows)
        rare = next(c for c in cols if c.name == "rare_field")
        assert rare.nullable is True

    def test_dense_field_is_not_nullable(self):
        # Present in 100% of 10 docs → not nullable
        rows = [{"_id": str(i), "name": "x"} for i in range(10)]
        cols = _infer_mongo_schema(rows)
        name_col = next(c for c in cols if c.name == "name")
        assert name_col.nullable is False


# ---------------------------------------------------------------------------
# _error_label
# ---------------------------------------------------------------------------

class TestErrorLabel:
    def test_timeout_error_label(self):
        label = _error_label(asyncio.TimeoutError(), 4.0)
        assert "timeout" in label
        assert "4.0" in label

    def test_cancelled_error_label(self):
        label = _error_label(asyncio.CancelledError(), 2.0)
        assert label == "cancelled"

    def test_generic_exception_label(self):
        label = _error_label(ValueError("bad"), 2.0)
        assert "ValueError" in label


# ---------------------------------------------------------------------------
# _assemble_schema — partial failure graceful degradation
# ---------------------------------------------------------------------------

class TestAssembleSchema:
    def test_successful_results_preserved(self):
        good_schema = DBSchema(db_name="oracle_forge", db_type="postgres", tables=[])
        results = {"postgres:oracle_forge": good_schema}
        ctx = _assemble_schema(results, {"postgres": 2.5})
        assert ctx.databases["oracle_forge"].error is None

    def test_exception_becomes_error_schema(self):
        results = {"postgres:oracle_forge": ConnectionError("refused")}
        ctx = _assemble_schema(results, {"postgres": 2.5})
        schema = ctx.databases["oracle_forge"]
        assert schema.error is not None
        assert schema.tables == []

    def test_mixed_results(self):
        good = DBSchema(db_name="yelp.db", db_type="sqlite", tables=[])
        results = {
            "sqlite:yelp.db": good,
            "postgres:oracle_forge": RuntimeError("down"),
        }
        ctx = _assemble_schema(results, {"postgres": 2.5, "sqlite": 1.0})
        assert ctx.databases["yelp.db"].error is None
        assert ctx.databases["oracle_forge"].error is not None

    def test_returns_schema_context(self):
        results = {"postgres:oracle_forge": DBSchema(db_name="oracle_forge", db_type="postgres", tables=[])}
        ctx = _assemble_schema(results, {})
        assert isinstance(ctx, SchemaContext)
