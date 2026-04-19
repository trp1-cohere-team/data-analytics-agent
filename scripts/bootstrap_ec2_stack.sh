#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/sqlite data/duckdb

if [ ! -f data/sqlite/main.db ]; then
  echo "Creating SQLite placeholder DB: data/sqlite/main.db"
  python3 - <<'PY'
import sqlite3, os
os.makedirs('data/sqlite', exist_ok=True)
con = sqlite3.connect('data/sqlite/main.db')
con.execute('CREATE TABLE IF NOT EXISTS healthcheck (id INTEGER PRIMARY KEY, note TEXT)')
con.commit()
con.close()
PY
fi

if [ ! -f data/duckdb/main.duckdb ]; then
  echo "Creating DuckDB placeholder DB: data/duckdb/main.duckdb"
  python3 - <<'PY'
import duckdb, os
os.makedirs('data/duckdb', exist_ok=True)
con = duckdb.connect('data/duckdb/main.duckdb')
con.execute('CREATE TABLE IF NOT EXISTS healthcheck (id INTEGER, note VARCHAR)')
con.close()
PY
fi

echo "Starting docker compose services..."
docker compose -f docker-compose.yml up -d

echo "Done. Run scripts/healthcheck_stack.sh next."
