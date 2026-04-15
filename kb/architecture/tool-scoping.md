# Tool Scoping and Selection

## Tool Registry (FR-03)

The ToolRegistry maps db_type hints to specific tool names:

| DB Hint | Tool Selected |
|---------|--------------|
| postgres, pg, postgresql | query_postgresql |
| mongodb, mongo | query_mongodb |
| sqlite | query_sqlite |
| duckdb | query_duckdb |

When no hint matches, the first available tool is returned.

## ToolPolicy Mutation Guard (SEC-05, SEC-11)

Blocked SQL keywords (word-boundary matching):
- INSERT, UPDATE, DELETE
- DROP, CREATE, ALTER

Note: `CREATED_AT` is NOT blocked (word boundary check prevents false positives).

## tools.yaml Structure

```yaml
sources:
  postgres_db: { kind: postgres }
  mongo_db: { kind: mongodb }
  sqlite_db: { kind: sqlite }
  duckdb_bridge: { kind: duckdb_bridge, read_only: true }

tools:
  query_postgresql: { kind: postgres-sql, source: postgres_db }
  query_mongodb: { kind: mongodb-aggregate, source: mongo_db }
  query_sqlite: { kind: sqlite-sql, source: sqlite_db }
  query_duckdb: { kind: duckdb_bridge_sql, source: duckdb_bridge }
```

## DuckDB Bridge Read-Only Contract (FR-03b)

- Only SELECT statements accepted
- Path fixed to `DUCKDB_PATH`
- Timeout: `DUCKDB_BRIDGE_TIMEOUT_SECONDS` (default 8s)
- Error types: `query` | `policy` | `config`
