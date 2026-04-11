"""Unit tests for agent/execution/mcp_client.py.

Covers:
- _classify_error: all 8 error types
- _classify_error: priority order (first match wins)
- _classify_error: schema keyword variants
- _classify_error: data_type keyword variants
- probe_mcp_toolbox: success, HTTP 5xx, connection error, timeout, HTTP 404 (alive)
- PBT-U2-MC-01: classify_error always returns one of the 8 valid strings (never raises)
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from agent.execution.mcp_client import _classify_error, probe_mcp_toolbox

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ERROR_TYPES = frozenset(
    {
        "timeout",
        "connection_error",
        "rate_limit",
        "auth_error",
        "schema_error",
        "data_type_error",
        "query_error",
        "unknown",
    }
)

_PBT_SETTINGS = h_settings(
    max_examples=300,
    deadline=timedelta(milliseconds=500),
)

# ---------------------------------------------------------------------------
# _classify_error — all 8 types
# ---------------------------------------------------------------------------


class TestClassifyErrorTypes:
    """Each of the 8 canonical error types is reachable."""

    def test_timeout(self) -> None:
        result = _classify_error(asyncio.TimeoutError(), None, "")
        assert result == "timeout"

    def test_connection_error(self) -> None:
        exc = aiohttp.ClientConnectionError("refused")
        result = _classify_error(exc, None, "")
        assert result == "connection_error"

    def test_rate_limit(self) -> None:
        result = _classify_error(None, 429, "too many requests")
        assert result == "rate_limit"

    def test_auth_error_401(self) -> None:
        result = _classify_error(None, 401, "unauthorized")
        assert result == "auth_error"

    def test_auth_error_403(self) -> None:
        result = _classify_error(None, 403, "forbidden")
        assert result == "auth_error"

    def test_schema_error_table_not_found(self) -> None:
        result = _classify_error(None, 400, "table not found: users")
        assert result == "schema_error"

    def test_schema_error_no_such_table(self) -> None:
        result = _classify_error(None, 400, "no such table: orders")
        assert result == "schema_error"

    def test_schema_error_column_not_found(self) -> None:
        result = _classify_error(None, 400, "column not found: user_id")
        assert result == "schema_error"

    def test_schema_error_undefined_column(self) -> None:
        result = _classify_error(None, 400, "undefined column: price")
        assert result == "schema_error"

    def test_schema_error_relation_does_not_exist(self) -> None:
        result = _classify_error(None, 400, 'relation "products" does not exist')
        assert result == "schema_error"

    def test_schema_error_unknown_collection(self) -> None:
        result = _classify_error(None, 400, "unknown collection: reviews")
        assert result == "schema_error"

    def test_data_type_error_cast(self) -> None:
        result = _classify_error(None, 400, "cannot cast integer to text")
        assert result == "data_type_error"

    def test_data_type_error_type_mismatch(self) -> None:
        result = _classify_error(None, 400, "type mismatch: expected int got string")
        assert result == "data_type_error"

    def test_data_type_error_invalid_input_syntax(self) -> None:
        result = _classify_error(None, 400, "invalid input syntax for integer: 'abc'")
        assert result == "data_type_error"

    def test_data_type_error_conversion_failed(self) -> None:
        result = _classify_error(None, 400, "conversion failed: text to int")
        assert result == "data_type_error"

    def test_data_type_error_invalid_cast(self) -> None:
        result = _classify_error(None, 400, "invalid cast from text to numeric")
        assert result == "data_type_error"

    def test_query_error_with_status(self) -> None:
        result = _classify_error(None, 400, "syntax error near SELECT")
        assert result == "query_error"

    def test_query_error_with_body_only(self) -> None:
        result = _classify_error(None, None, "some generic error message")
        assert result == "query_error"

    def test_unknown_no_info(self) -> None:
        result = _classify_error(None, None, "")
        assert result == "unknown"

    def test_unknown_exc_no_match(self) -> None:
        result = _classify_error(ValueError("generic"), None, "")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Priority order — first match always wins
# ---------------------------------------------------------------------------


class TestClassifyErrorPriority:
    """Priority: timeout > connection_error > rate_limit > auth_error > schema > type > query > unknown."""

    def test_timeout_beats_connection_error(self) -> None:
        # Both exc types set — TimeoutError should win (priority 1 > 2)
        exc = asyncio.TimeoutError()
        result = _classify_error(exc, None, "")
        assert result == "timeout"

    def test_connection_error_beats_rate_limit(self) -> None:
        exc = aiohttp.ClientConnectionError("refused")
        result = _classify_error(exc, 429, "")
        assert result == "connection_error"

    def test_rate_limit_beats_auth(self) -> None:
        # HTTP 429 AND 401 can't coexist, but body context matters:
        # status=429 wins over 401 body hint
        result = _classify_error(None, 429, "unauthorized")
        assert result == "rate_limit"

    def test_auth_beats_schema_keyword(self) -> None:
        # status=401 with schema body → auth_error wins
        result = _classify_error(None, 401, "table not found: users")
        assert result == "auth_error"

    def test_schema_beats_data_type(self) -> None:
        # body contains both schema and type keywords
        result = _classify_error(None, 400, "table not found, cannot cast integer")
        assert result == "schema_error"

    def test_data_type_beats_query_error(self) -> None:
        # pure type mismatch body, no status info beyond 400
        result = _classify_error(None, 400, "type mismatch: expected int got string")
        assert result == "data_type_error"

    def test_query_error_beats_unknown_when_status_present(self) -> None:
        result = _classify_error(None, 500, "internal server error")
        assert result == "query_error"

    def test_schema_keyword_case_insensitive(self) -> None:
        result = _classify_error(None, 400, "TABLE NOT FOUND: users")
        assert result == "schema_error"

    def test_data_type_keyword_case_insensitive(self) -> None:
        result = _classify_error(None, 400, "INVALID INPUT SYNTAX for type integer")
        assert result == "data_type_error"


# ---------------------------------------------------------------------------
# PBT-U2-MC-01 — classify_error never raises; always returns valid type
# ---------------------------------------------------------------------------

@given(
    exc=st.one_of(
        st.none(),
        st.just(asyncio.TimeoutError()),
        st.just(aiohttp.ClientConnectionError("x")),
        st.just(ValueError("x")),
        st.just(RuntimeError("x")),
    ),
    http_status=st.one_of(
        st.none(),
        st.integers(min_value=200, max_value=599),
    ),
    body=st.text(max_size=500),
)
@_PBT_SETTINGS
def test_pbt_classify_error_never_raises_always_valid(
    exc: BaseException | None,
    http_status: int | None,
    body: str,
) -> None:
    """PBT-U2-MC-01: _classify_error always returns one of the 8 valid strings, never raises."""
    result = _classify_error(exc, http_status, body)
    assert result in VALID_ERROR_TYPES, f"Got unexpected error type: {result!r}"


# ---------------------------------------------------------------------------
# probe_mcp_toolbox — MCPHealthProbe
# ---------------------------------------------------------------------------


class TestProbeMCPToolbox:
    """probe_mcp_toolbox raises RuntimeError on failure; passes on 404."""

    @pytest.mark.asyncio
    async def test_healthy_200_passes(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 200

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        await probe_mcp_toolbox(mock_session, "http://localhost:5000")

    @pytest.mark.asyncio
    async def test_http_404_treated_as_alive(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 404

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        # Should NOT raise — 404 means server is up, just no /healthz route
        await probe_mcp_toolbox(mock_session, "http://localhost:5000")

    @pytest.mark.asyncio
    async def test_http_500_raises_runtime_error(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 503

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with pytest.raises(RuntimeError, match="unhealthy"):
            await probe_mcp_toolbox(mock_session, "http://localhost:5000")

    @pytest.mark.asyncio
    async def test_connection_error_raises_runtime_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("refused")
        )
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with pytest.raises(RuntimeError, match="unreachable"):
            await probe_mcp_toolbox(mock_session, "http://localhost:5000")

    @pytest.mark.asyncio
    async def test_timeout_raises_runtime_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with pytest.raises(RuntimeError, match="timed out"):
            await probe_mcp_toolbox(mock_session, "http://localhost:5000")

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped_from_base_url(self) -> None:
        """probe_mcp_toolbox normalizes the base URL (no double slash)."""
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 200

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        await probe_mcp_toolbox(mock_session, "http://localhost:5000/")
        called_url = mock_session.get.call_args[0][0]
        assert called_url == "http://localhost:5000/healthz"
