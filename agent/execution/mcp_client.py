"""MCP Toolbox client for the Multi-DB Execution Engine.

Provides:
- MCPClient — injectable Protocol interface
- AiohttpMCPClient — production implementation
- _classify_error — 8-type PriorityErrorClassifier (SEC-U2-01, REL-U2-04)
- probe_mcp_toolbox — MCPHealthProbe (EagerConnectionGuard support)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

import aiohttp

logger = logging.getLogger("agent.execution.mcp_client")

# ---------------------------------------------------------------------------
# Error classification — 8-type priority decision tree
# ---------------------------------------------------------------------------

_SCHEMA_ERROR_KEYWORDS = (
    "table not found",
    "no such table",
    "column not found",
    "undefined column",
    "relation does not exist",
    "unknown collection",
)

_DATA_TYPE_ERROR_KEYWORDS = (
    "cast",
    "type mismatch",
    "invalid input syntax",
    "conversion failed",
    "cannot cast",
    "invalid cast",
)


def _classify_error(
    exc: BaseException | None,
    http_status: int | None,
    body: str,
) -> str:
    """Classify an MCP Toolbox error into one of 8 canonical types.

    Priority order (first match wins):
      1. asyncio.TimeoutError                    -> "timeout"
      2. aiohttp.ClientConnectionError           -> "connection_error"
      3. HTTP 429                                -> "rate_limit"
      4. HTTP 401 / 403                          -> "auth_error"
      5. body contains schema keywords           -> "schema_error"
      6. body contains type/cast keywords        -> "data_type_error"
      7. any HTTP error or body error present    -> "query_error"
      8. (fallback)                              -> "unknown"

    Never raises.
    """
    try:
        if isinstance(exc, asyncio.TimeoutError):
            return "timeout"
        if isinstance(exc, aiohttp.ClientConnectionError):
            return "connection_error"
        if http_status == 429:
            return "rate_limit"
        if http_status in (401, 403):
            return "auth_error"
        body_lower = body.lower() if body else ""
        if any(kw in body_lower for kw in _SCHEMA_ERROR_KEYWORDS):
            return "schema_error"
        if any(kw in body_lower for kw in _DATA_TYPE_ERROR_KEYWORDS):
            return "data_type_error"
        if http_status is not None or body_lower:
            return "query_error"
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# ---------------------------------------------------------------------------
# MCPHealthProbe — used by EagerConnectionGuard in __aenter__
# ---------------------------------------------------------------------------

async def probe_mcp_toolbox(
    session: aiohttp.ClientSession,
    base_url: str,
    timeout: float = 3.0,
) -> None:
    """Raise RuntimeError if MCP Toolbox is unreachable or returns 5xx.

    HTTP 404 is treated as alive (no /healthz endpoint but server is up).
    Called by MultiDBEngine.__aenter__ before allowing execute_plan calls.
    """
    url = base_url.rstrip("/") + "/healthz"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status >= 500:
                raise RuntimeError(
                    f"MCP Toolbox unhealthy: HTTP {resp.status} at {url}"
                )
            # HTTP 404 = server alive but no /healthz route → pass
    except aiohttp.ClientConnectionError as exc:
        raise RuntimeError(
            f"MCP Toolbox unreachable at {base_url}: {exc}"
        ) from exc
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"MCP Toolbox health check timed out ({timeout}s) at {base_url}"
        )


# ---------------------------------------------------------------------------
# MCPClient Protocol — injectable for testing
# ---------------------------------------------------------------------------

@runtime_checkable
class MCPClient(Protocol):
    """Minimal interface for calling MCP Toolbox tools.

    AiohttpMCPClient is the production implementation.
    Tests inject a mock satisfying this protocol.
    """

    async def call_tool(
        self, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Call a named MCP Toolbox tool with the given payload.

        Returns the raw response dict (expected to contain "result" key).
        Raises aiohttp.ClientError or asyncio.TimeoutError on network failure.
        """
        ...

    async def health_check(self, timeout: float = 3.0) -> bool:
        """Return True if MCP Toolbox is reachable; False otherwise."""
        ...


# ---------------------------------------------------------------------------
# AiohttpMCPClient — production implementation
# ---------------------------------------------------------------------------

class AiohttpMCPClient:
    """Production MCPClient using a shared aiohttp.ClientSession.

    The session is owned by MultiDBEngine and shared across all connectors
    for the lifetime of one async-context-manager block (RES-U2-01/02).

    SEC-U2-01: base_url is always sourced from config — never hardcoded here.
    """

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def call_tool(
        self, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST to /api/tool/{tool_name} and return the parsed JSON response.

        Raises:
            aiohttp.ClientError: on HTTP-level failure
            asyncio.TimeoutError: if the session timeout fires
            RuntimeError: if the response is not valid JSON
        """
        url = f"{self._base_url}/api/tool/{tool_name}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status >= 400:
                body = await resp.text()
                error_type = _classify_error(None, resp.status, body)
                logger.warning(
                    "mcp_tool_http_error",
                    extra={
                        "tool": tool_name,
                        "status": resp.status,
                        "error_type": error_type,
                    },
                )
                resp.raise_for_status()
            return await resp.json()

    async def health_check(self, timeout: float = 3.0) -> bool:
        """Return True if MCP Toolbox /healthz is reachable."""
        try:
            await probe_mcp_toolbox(self._session, self._base_url, timeout)
            return True
        except RuntimeError:
            return False
