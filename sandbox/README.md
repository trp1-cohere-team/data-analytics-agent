# Oracle Forge Sandbox

Local code-execution sandbox used by the agent runtime for isolated execution.

Contract:
- `GET /health` -> `{"status":"ok"}`
- `POST /execute` -> `{"result", "trace", "validation_status", "error_if_any"}`

Supported `mode` values for `POST /execute`:
- `sqlite_sql`: read-only SQL against a SQLite database file.
- `duckdb_sql`: read-only SQL against a DuckDB database file.
- `python_transform`: restricted Python transform function.

## Run locally
```bash
python3 sandbox/sandbox_server.py
```

## Example request
```bash
curl -sS -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{
    "mode":"sqlite_sql",
    "db_path":"./data/sqlite/main.db",
    "sql":"SELECT name FROM sqlite_master WHERE type='\''table'\'' LIMIT 5;",
    "row_limit":20
  }' | python3 -m json.tool
```

## Security guardrails
- Payload size limit (`SANDBOX_MAX_PAYLOAD_CHARS`, default `50000`).
- Path allowlist (`SANDBOX_ALLOWED_ROOTS`, default `<repo_root>,/tmp`).
- Mutating SQL blocked (`INSERT/UPDATE/DELETE/...`).
- Python mode runs in a subprocess with timeout (`SANDBOX_PY_TIMEOUT_SECONDS`, default `3`).
