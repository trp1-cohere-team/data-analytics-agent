#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== docker compose ps =="
docker compose -f docker-compose.yml ps

echo
echo "== MCP toolbox health =="
curl -sS --max-time 5 http://localhost:5000/health || true

echo
echo "== MCP toolbox tools/list =="
curl -sS --max-time 8 -X POST http://localhost:5000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' || true

echo
echo "== DuckDB bridge health =="
curl -sS --max-time 5 http://localhost:5001/health || true

echo
echo "== DuckDB bridge tools =="
curl -sS --max-time 5 http://localhost:5001/tools || true

echo
echo "== DuckDB bridge invoke =="
curl -sS --max-time 8 -X POST http://localhost:5001/invoke \
  -H 'Content-Type: application/json' \
  -d '{"tool":"query_duckdb","parameters":{"sql":"SELECT 1 AS ok"}}' || true

echo
echo "== Sandbox health =="
curl -sS --max-time 5 http://localhost:8080/health || true

echo
echo "== Sandbox execute =="
curl -sS --max-time 8 -X POST http://localhost:8080/execute \
  -H 'Content-Type: application/json' \
  -d '{"code":"print(1+1)","timeout":2}' || true
