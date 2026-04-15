"""Environment-driven configuration for the OracleForge Data Agent.

Reads all settings from environment variables with sensible defaults.
Provides offline stubs when ``AGENT_OFFLINE_MODE=1``.
Zero network calls on import.  No hardcoded secrets (NFR-04, SEC-09).
"""

from __future__ import annotations

import logging
import os
import uuid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, str(int(default)))
    return val.strip().lower() in ("1", "true", "yes")


def _int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.environ.get(key, str(default)))


def _str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Agent Runtime
# ---------------------------------------------------------------------------

AGENT_OFFLINE_MODE: bool = _bool("AGENT_OFFLINE_MODE", True)
AGENT_MAX_TOKENS: int = _int("AGENT_MAX_TOKENS", 700)
AGENT_TEMPERATURE: float = _float("AGENT_TEMPERATURE", 0.1)
AGENT_TIMEOUT_SECONDS: int = _int("AGENT_TIMEOUT_SECONDS", 45)
AGENT_SELF_CORRECTION_RETRIES: int = _int("AGENT_SELF_CORRECTION_RETRIES", 3)
AGENT_MAX_EXECUTION_STEPS: int = _int("AGENT_MAX_EXECUTION_STEPS", 6)
AGENT_USE_MCP: bool = _bool("AGENT_USE_MCP", True)
AGENT_USE_SANDBOX: bool = _bool("AGENT_USE_SANDBOX", False)

AGENT_SESSION_ID: str = _str("AGENT_SESSION_ID") or str(uuid.uuid4())

# ---------------------------------------------------------------------------
# MCP / Tool Layer
# ---------------------------------------------------------------------------

MCP_TOOLBOX_URL: str = _str("MCP_TOOLBOX_URL", "http://localhost:5000")
MCP_TIMEOUT_SECONDS: int = _int("MCP_TIMEOUT_SECONDS", 8)
TOOLS_YAML_PATH: str = _str("TOOLS_YAML_PATH", "./tools.yaml")

# SEC-09: no default pointing to a live server
DUCKDB_BRIDGE_URL: str = _str("DUCKDB_BRIDGE_URL", "")
DUCKDB_BRIDGE_TIMEOUT_SECONDS: int = _int("DUCKDB_BRIDGE_TIMEOUT_SECONDS", 8)
DUCKDB_PATH: str = _str("DUCKDB_PATH", "./data/duckdb/main.duckdb")

# ---------------------------------------------------------------------------
# OpenRouter LLM (FR-13)
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY: str = _str("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = _str("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
OPENROUTER_BASE_URL: str = _str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_APP_NAME: str = _str("OPENROUTER_APP_NAME", "oracle-forge-agent")

# ---------------------------------------------------------------------------
# Memory (FR-05)
# ---------------------------------------------------------------------------

AGENT_MEMORY_ROOT: str = _str("AGENT_MEMORY_ROOT", ".oracle_forge_memory")
AGENT_MEMORY_SESSION_ITEMS: int = _int("AGENT_MEMORY_SESSION_ITEMS", 12)
AGENT_MEMORY_TOPIC_CHARS: int = _int("AGENT_MEMORY_TOPIC_CHARS", 2500)
AGENT_RUNTIME_EVENTS_PATH: str = _str(
    "AGENT_RUNTIME_EVENTS_PATH", ".oracle_forge_memory/events.jsonl"
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AGENT_CONTEXT_PATH: str = _str("AGENT_CONTEXT_PATH", "agent/AGENT.md")
AGENT_CORRECTIONS_LOG_PATH: str = _str(
    "AGENT_CORRECTIONS_LOG_PATH", "kb/corrections/corrections_log.md"
)
KB_ROOT: str = "kb"

# ---------------------------------------------------------------------------
# Sandbox (FR-10)
# ---------------------------------------------------------------------------

SANDBOX_URL: str = _str("SANDBOX_URL", "http://localhost:8080")
SANDBOX_TIMEOUT_SECONDS: int = _int("SANDBOX_TIMEOUT_SECONDS", 12)
SANDBOX_MAX_PAYLOAD_CHARS: int = _int("SANDBOX_MAX_PAYLOAD_CHARS", 50000)
SANDBOX_PY_TIMEOUT_SECONDS: int = _int("SANDBOX_PY_TIMEOUT_SECONDS", 3)

# ---------------------------------------------------------------------------
# Logging Configuration (SEC-03)
# ---------------------------------------------------------------------------

LOG_LEVEL: str = _str("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Offline Stubs (NFR-01)
# ---------------------------------------------------------------------------

OFFLINE_LLM_RESPONSE: dict = {
    "choices": [
        {
            "message": {
                "content": (
                    "OFFLINE_STUB: This is a deterministic stub response "
                    "for offline mode testing."
                )
            }
        }
    ],
    "model": "offline-stub",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0},
}

OFFLINE_TOOL_LIST: list[dict] = [
    {
        "name": "query_postgresql",
        "kind": "postgres-sql",
        "source": "postgres_db",
        "description": "Execute read-only SQL against PostgreSQL",
    },
    {
        "name": "query_mongodb",
        "kind": "mongodb-aggregate",
        "source": "mongo_db",
        "description": "Execute aggregation pipeline against MongoDB",
    },
    {
        "name": "query_sqlite",
        "kind": "sqlite-sql",
        "source": "sqlite_db",
        "description": "Execute read-only SQL against SQLite",
    },
    {
        "name": "query_duckdb",
        "kind": "duckdb_bridge_sql",
        "source": "duckdb_bridge",
        "description": "Execute read-only SQL against DuckDB via custom MCP bridge",
    },
]

OFFLINE_INVOKE_RESULTS: dict[str, dict] = {
    "postgres": {
        "success": True,
        "result": [{"id": 1, "value": "stub_pg"}],
        "error": "",
    },
    "mongodb": {
        "success": True,
        "result": [{"_id": "1", "field": "stub_mongo"}],
        "error": "",
    },
    "sqlite": {
        "success": True,
        "result": [{"id": 1, "data": "stub_sqlite"}],
        "error": "",
    },
    "duckdb": {
        "success": True,
        "result": [{"col1": 42, "col2": "stub_duckdb"}],
        "error": "",
    },
}
