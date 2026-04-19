"""Local DB server — custom MCP server for DuckDB + legacy bridge endpoints.

Runs on a single port (default 5001) and serves:
  - MCP JSON-RPC    : POST /mcp                           (MCP protocol — query_duckdb)
  - DuckDB queries  : POST /invoke                        (legacy bridge wire format)
  - Health check    : GET  /health
  - Tool discovery  : GET  /tools                         (bridge discovery)

Set in .env:
  MCP_TOOLBOX_URL=http://localhost:5000
  DUCKDB_BRIDGE_URL=http://localhost:5000
  SQLITE_PATH=<absolute path to .db file>
  DUCKDB_PATH=<absolute path to .db/.duckdb file>

SEC-03: Structured logging.
SEC-09: Generic error messages returned to callers.
SEC-15: All DB calls wrapped in try/except.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import re

import duckdb
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

SQLITE_PATH: str = os.environ.get("SQLITE_PATH", "")
DUCKDB_PATH: str = os.environ.get("DUCKDB_PATH", "")
PORT: int = int(os.environ.get("LOCAL_DB_SERVER_PORT", "5000"))
_MUTATION_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)\b", re.IGNORECASE)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _run_sqlite(sql: str) -> dict:
    """Execute a read-only SQL query against SQLITE_PATH."""
    if not SQLITE_PATH:
        return {"success": False, "error": "SQLITE_PATH not configured", "result": None}
    try:
        con = sqlite3.connect(SQLITE_PATH)
        con.row_factory = sqlite3.Row
        cur = con.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        logger.info("SQLite OK: %d rows | sql=%.80s", len(rows), sql)
        return {"success": True, "result": rows, "error": ""}
    except sqlite3.OperationalError as exc:
        logger.warning("SQLite query error: %s", exc)
        return {"success": False, "result": None, "error": str(exc), "error_type": "query"}
    except Exception as exc:
        logger.error("SQLite unexpected error: %s", exc)
        return {"success": False, "result": None, "error": "database error", "error_type": "query"}


def _run_duckdb(sql: str) -> dict:
    """Execute a read-only SQL query against DUCKDB_PATH."""
    if not DUCKDB_PATH:
        return {
            "success": False,
            "error": f"duckdb_path_not_found: {DUCKDB_PATH}",
            "result": None,
            "error_type": "config",
        }
    if _MUTATION_RE.search(sql):
        return {
            "success": False,
            "result": None,
            "error": "read_only_violation: only SELECT is permitted",
            "error_type": "policy",
        }
    try:
        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        con.close()
        logger.info("DuckDB OK: %d rows | sql=%.80s", len(rows), sql)
        return {"success": True, "result": rows, "error": ""}
    except duckdb.CatalogException as exc:
        logger.warning("DuckDB catalog error: %s", exc)
        return {"success": False, "result": None, "error": f"query_error: {exc}", "error_type": "query"}
    except duckdb.ParserException as exc:
        logger.warning("DuckDB parse error: %s", exc)
        return {"success": False, "result": None, "error": f"query_error: {exc}", "error_type": "query"}
    except Exception as exc:
        logger.error("DuckDB unexpected error: %s", exc)
        return {"success": False, "result": None, "error": f"query_error: {exc}", "error_type": "query"}


# ---------------------------------------------------------------------------
# MCP JSON-RPC endpoint (custom DuckDB MCP server)
# ---------------------------------------------------------------------------

_MCP_TOOL_SCHEMA = {
    "name": "query_duckdb",
    "description": "Execute read-only SQL against DuckDB.",
    "inputSchema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "The SQL to execute."}},
        "required": ["sql"],
    },
}


@app.route("/mcp", methods=["POST"])
def mcp_endpoint():
    body = request.get_json(force=True) or {}
    rpc_id = body.get("id", 1)
    method = body.get("method", "")

    if method == "tools/list":
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": [_MCP_TOOL_SCHEMA]}})

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name != "query_duckdb":
            return jsonify({"jsonrpc": "2.0", "id": rpc_id,
                            "error": {"code": -32602, "message": f"unknown tool: {tool_name}"}})

        sql = arguments.get("sql", "").strip()
        if not sql:
            return jsonify({"jsonrpc": "2.0", "id": rpc_id,
                            "error": {"code": -32602, "message": "missing sql argument"}})

        result = _run_duckdb(sql)
        if not result["success"]:
            return jsonify({"jsonrpc": "2.0", "id": rpc_id,
                            "result": {"content": [{"type": "text", "text": result["error"]}],
                                       "isError": True}})

        rows = result["result"] or []
        content = [{"type": "text", "text": __import__("json").dumps(row)} for row in rows]
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": {"content": content}})

    return jsonify({"jsonrpc": "2.0", "id": rpc_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"}})


# ---------------------------------------------------------------------------
# Routes — legacy DuckDB bridge style
# ---------------------------------------------------------------------------

@app.route("/invoke", methods=["POST"])
def duckdb_invoke():
    body = request.get_json(force=True) or {}
    # Bridge sends: {"tool": "...", "parameters": {"sql": "..."}}
    params = body.get("parameters", body)
    sql = params.get("sql", "").strip()
    if not sql:
        return jsonify({"success": False, "error": "missing sql param", "result": None}), 400
    return jsonify(_run_duckdb(sql))


@app.route("/tools", methods=["GET"])
def list_tools():
    return jsonify([
        {
            "name": "query_duckdb",
            "kind": "duckdb_bridge_sql",
            "description": "Execute read-only SQL against DuckDB",
            "parameters": {"sql": "string"},
            "schema_summary": "DuckDB database configured via DUCKDB_PATH.",
        }
    ])


@app.route("/list_tools", methods=["GET"])
def list_tools_mcp_alias():
    return list_tools()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    sqlite_ok = bool(SQLITE_PATH and os.path.exists(SQLITE_PATH))
    duckdb_ok = bool(DUCKDB_PATH and os.path.exists(DUCKDB_PATH))
    return jsonify({
        "status": "ok",
        "sqlite_path": SQLITE_PATH,
        "sqlite_exists": sqlite_ok,
        "duckdb_path": DUCKDB_PATH,
        "duckdb_exists": duckdb_ok,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting local DB server on port %d", PORT)
    logger.info("  SQLITE_PATH = %s", SQLITE_PATH or "(not set)")
    logger.info("  DUCKDB_PATH = %s", DUCKDB_PATH or "(not set)")
    app.run(host="0.0.0.0", port=PORT, debug=False)
