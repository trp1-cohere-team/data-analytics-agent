"""SchemaIntrospector — auto-introspects all 4 DB types via MCP Toolbox.

Uses a bulkhead timeout pattern:
- Outer ceiling: 9s (OUTER_INTROSPECT_TIMEOUT)
- Per-DB sub-limits: mongodb=4s, postgres=2.5s, duckdb=1.5s, sqlite=1s
- Partial failures return empty DBSchema with error field — never block startup
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from agent.config import settings
from agent.models import (
    ColumnSchema,
    DBSchema,
    ForeignKeyRelationship,
    SchemaContext,
    TableSchema,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP client protocol (dependency injection for testability)
# ---------------------------------------------------------------------------

class MCPClient(Protocol):
    """Protocol for MCP Toolbox HTTP client. Injected to allow mocking in tests."""

    async def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP Toolbox tool and return the parsed JSON response."""
        ...


# ---------------------------------------------------------------------------
# Default aiohttp-based client
# ---------------------------------------------------------------------------

class AiohttpMCPClient:
    """Production MCP Toolbox client using aiohttp."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        import aiohttp
        url = f"{self._base_url}/v1/tools/{tool_name}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Graceful schema assembler
# ---------------------------------------------------------------------------

def _error_label(exc: BaseException, db_timeout: float) -> str:
    """Map an exception to a human-readable error field value."""
    if isinstance(exc, asyncio.TimeoutError):
        return f"timeout_{db_timeout}s"
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    try:
        import aiohttp
        if isinstance(exc, aiohttp.ClientError):
            return f"connection_error: {exc}"
    except ImportError:
        pass
    return f"introspection_error: {type(exc).__name__}"


def _assemble_schema(
    results: dict[str, DBSchema | BaseException],
    db_timeouts: dict[str, float],
) -> SchemaContext:
    """Convert gather results (mix of DBSchema and exceptions) into SchemaContext."""
    databases: dict[str, DBSchema] = {}
    for db_key, result in results.items():
        db_type = db_key.split(":")[0]  # e.g. "postgres:mydb" → "postgres"
        db_name = db_key.split(":", 1)[1] if ":" in db_key else db_key
        if isinstance(result, DBSchema):
            databases[db_name] = result
        else:
            timeout = db_timeouts.get(db_type, 9.0)
            databases[db_name] = DBSchema(
                db_name=db_name,
                db_type=db_type,
                tables=[],
                error=_error_label(result, timeout),
            )
    return SchemaContext(databases=databases)


# ---------------------------------------------------------------------------
# Per-DB introspection (Standard depth: tables, columns, types, nullable, PKs, FKs)
# ---------------------------------------------------------------------------

async def introspect_postgres(db_name: str, client: MCPClient) -> DBSchema:
    """Introspect PostgreSQL via information_schema (Standard depth)."""
    try:
        col_result = await client.call_tool("postgres_query", {
            "query": (
                "SELECT table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position"
            )
        })
        pk_result = await client.call_tool("postgres_query", {
            "query": (
                "SELECT tc.table_name, kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "  AND tc.table_schema = kcu.table_schema "
                "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'"
            )
        })
        fk_result = await client.call_tool("postgres_query", {
            "query": (
                "SELECT tc.table_name, kcu.column_name, "
                "ccu.table_name AS foreign_table, ccu.column_name AS foreign_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"
            )
        })
        return _build_schema_from_rows(
            db_name, "postgres", col_result["result"], pk_result["result"], fk_result["result"]
        )
    except Exception as exc:
        logger.warning("PostgreSQL introspection failed: %s", exc)
        return DBSchema(db_name=db_name, db_type="postgres", error=str(exc))


async def introspect_sqlite(db_path: str, client: MCPClient) -> DBSchema:
    """Introspect SQLite via sqlite_master and PRAGMA."""
    try:
        tables_result = await client.call_tool("sqlite_query", {
            "query": "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        })
        table_names: list[str] = [row["name"] for row in tables_result["result"]]

        tables: list[TableSchema] = []
        for tname in table_names:
            col_result = await client.call_tool("sqlite_query", {
                "query": f"PRAGMA table_info({tname})"
            })
            fk_result = await client.call_tool("sqlite_query", {
                "query": f"PRAGMA foreign_key_list({tname})"
            })
            columns = [
                ColumnSchema(
                    name=row["name"],
                    data_type=row["type"] or "TEXT",
                    nullable=not bool(row["notnull"]),
                    is_primary_key=bool(row["pk"]),
                )
                for row in col_result["result"]
            ]
            fks = [
                ForeignKeyRelationship(
                    from_table=tname,
                    from_column=row["from"],
                    to_table=row["table"],
                    to_column=row["to"],
                )
                for row in fk_result["result"]
            ]
            tables.append(TableSchema(name=tname, columns=columns, foreign_keys=fks))

        return DBSchema(db_name=db_path, db_type="sqlite", tables=tables)
    except Exception as exc:
        logger.warning("SQLite introspection failed: %s", exc)
        return DBSchema(db_name=db_path, db_type="sqlite", error=str(exc))


async def introspect_mongodb(db_name: str, client: MCPClient) -> DBSchema:
    """Introspect MongoDB by sampling 100 documents per collection."""
    try:
        coll_result = await client.call_tool("mongodb_aggregate", {
            "pipeline": [{"$listCollections": {}}],
            "collection": "system.namespaces",
        })
        collection_names: list[str] = [
            row.get("name", "") for row in coll_result.get("result", [])
            if row.get("name") and not row["name"].startswith("system.")
        ]

        tables: list[TableSchema] = []
        for cname in collection_names:
            sample_result = await client.call_tool("mongodb_aggregate", {
                "pipeline": [{"$sample": {"size": 100}}],
                "collection": cname,
            })
            rows: list[dict[str, Any]] = sample_result.get("result", [])
            columns = _infer_mongo_schema(rows)
            tables.append(TableSchema(name=cname, columns=columns, foreign_keys=[]))

        return DBSchema(db_name=db_name, db_type="mongodb", tables=tables)
    except Exception as exc:
        logger.warning("MongoDB introspection failed: %s", exc)
        return DBSchema(db_name=db_name, db_type="mongodb", error=str(exc))


async def introspect_duckdb(db_path: str, client: MCPClient) -> DBSchema:
    """Introspect DuckDB via information_schema."""
    try:
        col_result = await client.call_tool("duckdb_query", {
            "query": (
                "SELECT table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'main' "
                "ORDER BY table_name, ordinal_position"
            )
        })
        pk_result = await client.call_tool("duckdb_query", {
            "query": (
                "SELECT table_name, column_name "
                "FROM information_schema.key_column_usage kcu "
                "JOIN information_schema.table_constraints tc "
                "  ON kcu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'PRIMARY KEY'"
            )
        })
        return _build_schema_from_rows(
            db_path, "duckdb", col_result["result"], pk_result["result"], []
        )
    except Exception as exc:
        logger.warning("DuckDB introspection failed: %s", exc)
        return DBSchema(db_name=db_path, db_type="duckdb", error=str(exc))


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

async def introspect_all(
    mcp_toolbox_url: str | None = None,
    client: MCPClient | None = None,
) -> SchemaContext:
    """Introspect all connected databases using the bulkhead timeout pattern.

    - Outer ceiling: settings.outer_introspect_timeout (9s)
    - Per-DB: settings.db_timeouts
    - Partial failures → empty DBSchema with error field (SI-01, SI-03)
    """
    url = mcp_toolbox_url or settings.mcp_toolbox_url
    mcp = client or AiohttpMCPClient(url)
    db_timeouts = settings.db_timeouts

    async def _with_timeout(coro: Any, db_type: str) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=db_timeouts.get(db_type, 2.0))
        except Exception as exc:
            return exc

    tasks = {
        "mongodb:oracle_forge": _with_timeout(introspect_mongodb("oracle_forge", mcp), "mongodb"),
        "postgres:oracle_forge": _with_timeout(introspect_postgres("oracle_forge", mcp), "postgres"),
        "duckdb:data/analytics.duckdb": _with_timeout(introspect_duckdb("data/analytics.duckdb", mcp), "duckdb"),
        "sqlite:data/yelp.db": _with_timeout(introspect_sqlite("data/yelp.db", mcp), "sqlite"),
    }

    try:
        async with asyncio.timeout(settings.outer_introspect_timeout):
            raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    except asyncio.TimeoutError:
        logger.warning("Outer introspection timeout (%ss) reached", settings.outer_introspect_timeout)
        raw_results = list(tasks.values())  # whatever completed; gather handles partials

    results = dict(zip(tasks.keys(), raw_results))
    schema = _assemble_schema(results, db_timeouts)

    ok = sum(1 for db in schema.databases.values() if db.error is None)
    failed = len(schema.databases) - ok
    logger.info("Schema introspection complete: %d ok, %d failed", ok, failed)
    return schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_schema_from_rows(
    db_name: str,
    db_type: str,
    col_rows: list[dict[str, Any]],
    pk_rows: list[dict[str, Any]],
    fk_rows: list[dict[str, Any]],
) -> DBSchema:
    """Build DBSchema from flat information_schema row lists."""
    pk_set: set[tuple[str, str]] = {(r["table_name"], r["column_name"]) for r in pk_rows}

    tables_map: dict[str, list[ColumnSchema]] = {}
    for row in col_rows:
        tname = row["table_name"]
        col = ColumnSchema(
            name=row["column_name"],
            data_type=row["data_type"],
            nullable=row.get("is_nullable", "YES") == "YES",
            is_primary_key=(tname, row["column_name"]) in pk_set,
        )
        tables_map.setdefault(tname, []).append(col)

    fks_map: dict[str, list[ForeignKeyRelationship]] = {}
    for row in fk_rows:
        fk = ForeignKeyRelationship(
            from_table=row["table_name"],
            from_column=row["column_name"],
            to_table=row["foreign_table"],
            to_column=row["foreign_column"],
        )
        fks_map.setdefault(row["table_name"], []).append(fk)

    tables = [
        TableSchema(name=tname, columns=cols, foreign_keys=fks_map.get(tname, []))
        for tname, cols in tables_map.items()
    ]
    return DBSchema(db_name=db_name, db_type=db_type, tables=tables)


def _infer_mongo_schema(rows: list[dict[str, Any]]) -> list[ColumnSchema]:
    """Infer column schema from MongoDB sample documents."""
    if not rows:
        return [ColumnSchema(name="_id", data_type="ObjectId", nullable=False, is_primary_key=True)]

    field_types: dict[str, set[str]] = {}
    field_counts: dict[str, int] = {}

    for row in rows:
        for key, val in row.items():
            field_counts[key] = field_counts.get(key, 0) + 1
            field_types.setdefault(key, set()).add(type(val).__name__)

    n = len(rows)
    columns: list[ColumnSchema] = []
    for field_name, count in field_counts.items():
        types = field_types[field_name]
        data_type = next(iter(types)) if len(types) == 1 else "mixed"
        nullable = count < n * 0.9  # SI-02: < 10% presence → nullable
        columns.append(
            ColumnSchema(
                name=field_name,
                data_type=data_type,
                nullable=nullable,
                is_primary_key=field_name == "_id",
            )
        )
    return columns
