# Shared Infrastructure
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Scope**: Project-wide infrastructure shared across all units

---

## MCP Toolbox for Databases

**Shared by**: U2 (MultiDBEngine — runtime queries), U5 (SchemaIntrospector — startup introspection)

### Process

| Property | Value |
|---|---|
| Binary | `mcp-toolbox` (Google MCP Toolbox for Databases) |
| Start command | `mcp-toolbox serve --config tools.yaml` |
| Listen address | `http://localhost:5000` |
| Config file | `tools.yaml` (workspace root) |
| Must start before | Agent server (U1) |

### tools.yaml Structure

```yaml
sources:
  postgres-db:
    kind: postgres
    host: localhost
    port: 5432
    database: oracle_forge
    user: ${POSTGRES_USER}
    password: ${POSTGRES_PASSWORD}

  sqlite-db:
    kind: sqlite
    database: data/yelp.db

  mongodb-db:
    kind: mongodb
    uri: mongodb://localhost:27017
    database: oracle_forge

  duckdb-db:
    kind: duckdb
    database: data/analytics.duckdb

tools:
  postgres_query:
    kind: postgres-sql
    source: postgres-db
    description: Execute a SQL query against PostgreSQL

  sqlite_query:
    kind: sqlite-sql
    source: sqlite-db
    description: Execute a SQL query against SQLite

  mongodb_aggregate:
    kind: mongodb-aggregate
    source: mongodb-db
    description: Execute a MongoDB aggregation pipeline

  duckdb_query:
    kind: duckdb-sql
    source: duckdb-db
    description: Execute an analytical SQL query against DuckDB
```

### HTTP Protocol

All agent calls to MCP Toolbox follow this pattern:

```
POST http://localhost:5000/v1/tools/{tool_name}
Content-Type: application/json

{
  "query": "SELECT ...",      // for SQL tools
  "params": {}                // optional bind parameters
}

// MongoDB:
{
  "pipeline": [...],
  "collection": "collection_name"
}
```

Response:
```json
{
  "result": [...],            // list of row dicts
  "columns": ["col1", ...],   // column names
  "row_count": 42
}
```

Error response:
```json
{
  "error": "syntax_error",
  "message": "..."
}
```

---

## Shared Python Package Files

| File | Owner | Shared With |
|---|---|---|
| `agent/models.py` | Shared infrastructure | U1, U2, U3, U4, U5 |
| `agent/config.py` | Shared infrastructure | U1, U2, U3, U5 |
| `requirements.txt` | Project-wide | All units |
| `pyproject.toml` | Project-wide | All units |
| `tools.yaml` | MCP Toolbox config | U2, U5 |
| `.env` | Runtime secrets | U1 (config.py reads it) |

---

## Environment Variables (.env)

```bash
# LLM
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o

# MCP Toolbox
MCP_TOOLBOX_URL=http://localhost:5000

# Databases (read by MCP Toolbox, not agent directly)
POSTGRES_USER=oracle_forge
POSTGRES_PASSWORD=...

# Agent
AGENT_PORT=8000
```

`.env` is never committed to version control. `.env.example` (committed) documents all required variables with placeholder values.

---

## Required Services by Unit

| Unit | MCP Toolbox | PostgreSQL | SQLite | MongoDB | DuckDB | OpenRouter |
|---|---|---|---|---|---|---|
| U1 — Agent Core | Indirect (via U2) | — | — | — | — | Required |
| U2 — MultiDB Engine | Required (queries) | Required | Required | Required | Required | — |
| U3 — KB & Memory | — | — | — | — | — | — |
| U4 — Eval Harness | — | — | — | — | — | Required (judge) |
| U5 — Utilities | Required (introspect) | — | — | — | — | — |
