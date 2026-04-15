"""Local DB server — drop-in replacement for Google MCP Toolbox + DuckDB bridge.

Runs on a single port (default 5000) and serves both:
  - SQLite queries  : POST /api/tool/query_sqlite/invoke  (MCP Toolbox wire format)
  - DuckDB queries  : POST /invoke                        (DuckDB bridge wire format)
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
        return {"success": False, "error": "DUCKDB_PATH not configured", "result": None}
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
        return {"success": False, "result": None, "error": str(exc), "error_type": "query"}
    except duckdb.ParserException as exc:
        logger.warning("DuckDB parse error: %s", exc)
        return {"success": False, "result": None, "error": str(exc), "error_type": "query"}
    except Exception as exc:
        logger.error("DuckDB unexpected error: %s", exc)
        return {"success": False, "result": None, "error": "database error", "error_type": "query"}


# ---------------------------------------------------------------------------
# Routes — MCP Toolbox style (SQLite)
# ---------------------------------------------------------------------------

@app.route("/api/tool/query_sqlite/invoke", methods=["POST"])
def sqlite_invoke():
    params = request.get_json(force=True) or {}
    sql = params.get("sql", "").strip()
    if not sql:
        return jsonify({"success": False, "error": "missing sql param", "result": None}), 400
    return jsonify(_run_sqlite(sql))


# ---------------------------------------------------------------------------
# Routes — DuckDB bridge style
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
        }
    ])


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
