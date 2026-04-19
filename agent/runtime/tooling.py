"""Tool registry and policy enforcement.

FR-03: ToolRegistry maps db-type hints to MCP tools.
SEC-05 / SEC-11: ToolPolicy blocks SQL mutation keywords before invocation.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agent.data_agent.config import AGENT_USE_SANDBOX, SANDBOX_MAX_PAYLOAD_CHARS
from agent.data_agent.mcp_toolbox_client import MCPClient
from agent.data_agent.types import ToolDescriptor
from utils.db_utils import db_type_from_kind

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mutation keyword blocking (SEC-05)
# Word-boundary match to avoid false positives like CREATED_AT
# ---------------------------------------------------------------------------

_MUTATION_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER")
_MUTATION_RE = re.compile(
    r"\b(" + "|".join(_MUTATION_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# DB hint normalisation
# ---------------------------------------------------------------------------

_HINT_TO_DB_TYPE: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "pg": "postgres",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "duck": "duckdb",
}


class ToolRegistry:
    """Maps db-type hints to MCP tools from the unified 4-tool registry."""

    def __init__(self, mcp_client: MCPClient) -> None:
        self._client = mcp_client
        self._tools = mcp_client.discover_tools()
        if AGENT_USE_SANDBOX:
            # Optional execution path for Python code blocks (FR-10).
            self._tools.append(
                ToolDescriptor(
                    name="execute_python",
                    kind="sandbox-python",
                    source="sandbox",
                    description="Execute Python code in the isolated sandbox server.",
                    parameters={"code": "string"},
                )
            )
        self._by_name: dict[str, ToolDescriptor] = {t.name: t for t in self._tools}
        self._by_db_type: dict[str, ToolDescriptor] = {}
        for t in self._tools:
            dt = db_type_from_kind(t.kind)
            if dt != "unknown":
                self._by_db_type[dt] = t

    def get_tools(self) -> list[ToolDescriptor]:
        """Return all registered tools."""
        return list(self._tools)

    def select_tool(self, db_hints: list[str]) -> Optional[ToolDescriptor]:
        """Select best tool for given db hints.

        Returns ``None`` if no tools are registered.
        """
        if not self._tools:
            return None

        for hint in db_hints:
            normalised = _HINT_TO_DB_TYPE.get(hint.lower().strip(), hint.lower().strip())
            if normalised in self._by_db_type:
                return self._by_db_type[normalised]

        # Fallback: return first tool
        return self._tools[0] if self._tools else None

    def get_tool_by_name(self, name: str) -> Optional[ToolDescriptor]:
        """Look up a tool by its registered name."""
        return self._by_name.get(name)


class ToolPolicy:
    """Security barrier — validates tool invocations before execution.

    Blocks SQL mutation keywords (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER)
    and enforces payload size limits.  This is a defense-in-depth layer;
    backends also enforce read-only.
    """

    def validate_invocation(
        self, tool_name: str, params: dict
    ) -> tuple[bool, str]:
        """Validate a tool invocation.

        Returns ``(True, "")`` if valid, ``(False, reason)`` if blocked.
        """
        if not tool_name:
            return False, "empty tool_name"

        if not isinstance(params, dict):
            return False, "params must be a dict"

        sql = params.get("sql")
        if sql is not None:
            if not isinstance(sql, str):
                return False, "sql param must be a string"

            # Size cap
            if len(sql) > SANDBOX_MAX_PAYLOAD_CHARS:
                return False, f"sql exceeds max {SANDBOX_MAX_PAYLOAD_CHARS} chars"

            # Mutation keyword check (word-boundary to avoid false positives)
            match = _MUTATION_RE.search(sql)
            if match:
                keyword = match.group(1).upper()
                return False, f"mutation_blocked: {keyword}"

        return True, ""
