"""Unified MCP client facade for all 4 database types.

FR-03: Single public entry point. Reads tools.yaml at init to build
the 4-tool registry.  Dispatches by ``kind`` field:
  - postgres-sql / mongodb-aggregate / sqlite-sql → Google MCP Toolbox
  - duckdb_bridge_sql → DuckDBBridgeClient (private)

Upstream modules (ToolRegistry, conductor, planner, synthesizer) import
only this module.  They never import duckdb_bridge_client.py directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import requests

from agent.data_agent.config import (
    AGENT_OFFLINE_MODE,
    AGENT_USE_MCP,
    MCP_TIMEOUT_SECONDS,
    MCP_TOOLBOX_URL,
    OFFLINE_INVOKE_RESULTS,
    OFFLINE_TOOL_LIST,
    TOOLS_YAML_PATH,
)
from agent.data_agent.duckdb_bridge_client import DuckDBBridgeClient
from agent.data_agent.types import InvokeResult, ToolDescriptor
from utils.db_utils import db_type_from_kind

logger = logging.getLogger(__name__)

# Standard kinds handled by Google MCP Toolbox
_TOOLBOX_KINDS = frozenset({"postgres-sql", "mongodb-aggregate", "sqlite-sql"})
_BRIDGE_KIND = "duckdb_bridge_sql"


class MCPClient:
    """Unified MCP client for all 4 database tools.

    Loads ``tools.yaml`` at init and builds an immutable 4-tool registry.
    ``discover_tools()`` returns the flat list without querying backends.
    ``invoke_tool()`` dispatches internally by the tool's ``kind`` field.
    """

    def __init__(self) -> None:
        self._registry: dict[str, ToolDescriptor] = {}
        self._bridge = DuckDBBridgeClient()

        if AGENT_OFFLINE_MODE or not AGENT_USE_MCP:
            self._load_offline_registry()
        else:
            self._load_yaml_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_tools(self) -> list[ToolDescriptor]:
        """Return all 4 tools from the registry.

        No backend is queried — the registry is populated at init.
        """
        return list(self._registry.values())

    def invoke_tool(self, tool_name: str, params: dict) -> InvokeResult:
        """Invoke a tool by name, dispatching to the correct backend.

        Parameters
        ----------
        tool_name : str
            One of the 4 registered tool names.
        params : dict
            Tool-specific parameters (e.g. ``{"sql": "SELECT ..."}``).
        """
        tool = self._registry.get(tool_name)
        if tool is None:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error=f"unknown_tool: '{tool_name}' not in registry",
                error_type="config",
            )

        db_type = db_type_from_kind(tool.kind)

        # Offline mode — return stubs for any DB type
        if AGENT_OFFLINE_MODE:
            return self._offline_invoke(tool_name, db_type)

        # Dispatch by kind
        if tool.kind in _TOOLBOX_KINDS:
            return self._invoke_toolbox(tool, params, db_type)
        elif tool.kind == _BRIDGE_KIND:
            return self._bridge.invoke(tool_name, params)
        else:
            return InvokeResult(
                success=False,
                tool_name=tool_name,
                error=f"unsupported_kind: '{tool.kind}'",
                error_type="config",
                db_type=db_type,
            )

    # ------------------------------------------------------------------
    # Registry loaders
    # ------------------------------------------------------------------

    def _load_yaml_registry(self) -> None:
        """Load tool definitions from tools.yaml."""
        try:
            import yaml  # deferred import — only needed in online mode

            with open(TOOLS_YAML_PATH, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            logger.warning("tools.yaml not found at %s — using empty registry", TOOLS_YAML_PATH)
            return
        except Exception as exc:
            logger.warning("Failed to parse tools.yaml: %s — using empty registry", exc)
            return

        tools_section = data.get("tools", {})
        for name, spec in tools_section.items():
            self._registry[name] = ToolDescriptor(
                name=name,
                kind=spec.get("kind", ""),
                source=spec.get("source", ""),
                description=spec.get("description", ""),
            )

        logger.info(
            "MCPClient: loaded %d tools from %s", len(self._registry), TOOLS_YAML_PATH
        )

    def _load_offline_registry(self) -> None:
        """Build registry from offline stubs."""
        for item in OFFLINE_TOOL_LIST:
            self._registry[item["name"]] = ToolDescriptor(
                name=item["name"],
                kind=item["kind"],
                source=item["source"],
                description=item["description"],
            )
        logger.info("MCPClient: loaded %d offline tools", len(self._registry))

    # ------------------------------------------------------------------
    # Backend dispatchers
    # ------------------------------------------------------------------

    def _invoke_toolbox(
        self, tool: ToolDescriptor, params: dict, db_type: str
    ) -> InvokeResult:
        """Dispatch to Google MCP Toolbox at ``MCP_TOOLBOX_URL``."""
        try:
            resp = requests.post(
                f"{MCP_TOOLBOX_URL}/api/tool/{tool.name}/invoke",
                json=params,
                timeout=MCP_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            return InvokeResult(
                success=False,
                tool_name=tool.name,
                error="timeout",
                error_type="timeout",
                db_type=db_type,
            )
        except requests.ConnectionError:
            return InvokeResult(
                success=False,
                tool_name=tool.name,
                error="connection_refused",
                error_type="config",
                db_type=db_type,
            )
        except (requests.RequestException, json.JSONDecodeError) as exc:
            return InvokeResult(
                success=False,
                tool_name=tool.name,
                error=f"toolbox_error: {exc}",
                error_type="config",
                db_type=db_type,
            )

        return InvokeResult(
            success=data.get("success", True),
            tool_name=tool.name,
            result=data.get("result"),
            error=data.get("error", ""),
            error_type=data.get("error_type", ""),
            db_type=db_type,
        )

    @staticmethod
    def _offline_invoke(tool_name: str, db_type: str) -> InvokeResult:
        """Return offline stub result for the given db_type."""
        stub = OFFLINE_INVOKE_RESULTS.get(db_type, {})
        return InvokeResult(
            success=stub.get("success", True),
            tool_name=tool_name,
            result=stub.get("result"),
            error=stub.get("error", ""),
            db_type=db_type,
        )
