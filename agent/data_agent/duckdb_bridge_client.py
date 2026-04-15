"""Private DuckDB MCP bridge client.

FR-03b: Speaks the custom DuckDB bridge wire protocol.
- Schema discovery: GET {DUCKDB_BRIDGE_URL}/tools
- Query execution: POST {DUCKDB_BRIDGE_URL}/invoke

**PRIVATE**: Imported ONLY by mcp_toolbox_client.py. No other module
should reference this file.

SEC-05: SQL length validation before sending.
SEC-13: JSON response parsing with try/except.
SEC-15: Explicit error handling for all HTTP calls.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from agent.data_agent.config import (
    AGENT_OFFLINE_MODE,
    DUCKDB_BRIDGE_TIMEOUT_SECONDS,
    DUCKDB_BRIDGE_URL,
    OFFLINE_INVOKE_RESULTS,
    OFFLINE_TOOL_LIST,
    SANDBOX_MAX_PAYLOAD_CHARS,
)
from agent.data_agent.types import InvokeResult, ToolDescriptor

logger = logging.getLogger(__name__)


class DuckDBBridgeClient:
    """Client for the custom DuckDB MCP bridge server.

    This class is a **private implementation detail** of :class:`MCPClient`
    in ``mcp_toolbox_client.py``.  It must not be imported by any other
    module.
    """

    def __init__(self) -> None:
        self._url = DUCKDB_BRIDGE_URL
        self._timeout = DUCKDB_BRIDGE_TIMEOUT_SECONDS

    # ------------------------------------------------------------------
    # Schema discovery
    # ------------------------------------------------------------------

    def discover_tools(self) -> list[ToolDescriptor]:
        """Return tool descriptors from the DuckDB bridge.

        In offline mode, returns a stub descriptor built from
        ``OFFLINE_TOOL_LIST``.
        """
        if AGENT_OFFLINE_MODE:
            return self._offline_tool_list()

        if not self._url:
            logger.warning("DUCKDB_BRIDGE_URL is not configured — no DuckDB tools")
            return []

        try:
            resp = requests.get(
                f"{self._url}/tools",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            logger.warning("DuckDB bridge discovery timed out")
            return []
        except requests.ConnectionError:
            logger.warning("DuckDB bridge unreachable at %s", self._url)
            return []
        except (requests.RequestException, json.JSONDecodeError) as exc:
            logger.warning("DuckDB bridge discovery failed: %s", exc)
            return []

        tools: list[ToolDescriptor] = []
        items = data if isinstance(data, list) else data.get("tools", [])
        for item in items:
            tools.append(
                ToolDescriptor(
                    name=item.get("name", "query_duckdb"),
                    kind="duckdb_bridge_sql",
                    source="duckdb_bridge",
                    description=item.get("description", ""),
                    parameters=item.get("parameters", {}),
                    schema_summary=item.get("schema_summary", ""),
                )
            )
        return tools

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def invoke(self, tool_name: str, params: dict) -> InvokeResult:
        """Execute a query against the DuckDB bridge.

        In offline mode, returns a stub result from ``OFFLINE_INVOKE_RESULTS``.
        """
        if AGENT_OFFLINE_MODE:
            return self._offline_invoke(tool_name)

        if not self._url:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error="DUCKDB_BRIDGE_URL is not configured",
                error_type="config",
                db_type="duckdb",
            )

        # SEC-05: validate SQL length
        sql = params.get("sql", "")
        if len(sql) > SANDBOX_MAX_PAYLOAD_CHARS:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error=f"SQL payload exceeds max {SANDBOX_MAX_PAYLOAD_CHARS} chars",
                error_type="policy",
                db_type="duckdb",
            )

        try:
            resp = requests.post(
                f"{self._url}/invoke",
                json={"tool": tool_name, "parameters": {"sql": sql}},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error="timeout",
                error_type="timeout",
                db_type="duckdb",
            )
        except requests.ConnectionError:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error="connection_refused",
                error_type="config",
                db_type="duckdb",
            )
        except (requests.RequestException, json.JSONDecodeError) as exc:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error=f"bridge_error: {exc}",
                error_type="config",
                db_type="duckdb",
            )

        return InvokeResult(
            success=data.get("success", False),
            tool_name=tool_name,
            result=data.get("result"),
            error=data.get("error", ""),
            error_type=data.get("error_type", ""),
            db_type="duckdb",
        )

    # ------------------------------------------------------------------
    # Offline stubs
    # ------------------------------------------------------------------

    @staticmethod
    def _offline_tool_list() -> list[ToolDescriptor]:
        for item in OFFLINE_TOOL_LIST:
            if item["kind"] == "duckdb_bridge_sql":
                return [
                    ToolDescriptor(
                        name=item["name"],
                        kind=item["kind"],
                        source=item["source"],
                        description=item["description"],
                    )
                ]
        return []

    @staticmethod
    def _offline_invoke(tool_name: str) -> InvokeResult:
        stub = OFFLINE_INVOKE_RESULTS.get("duckdb", {})
        return InvokeResult(
            success=stub.get("success", True),
            tool_name=tool_name,
            result=stub.get("result"),
            error=stub.get("error", ""),
            db_type="duckdb",
        )
