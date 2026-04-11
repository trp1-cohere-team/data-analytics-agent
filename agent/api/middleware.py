"""ASGI middleware for AgentAPI.

Design decisions:
  - Pattern 3: ASGISecurityMiddleware — adds 3 headers to every response
  - Pattern 4: DualLayerErrorHandler Layer B — catches ASGI-level exceptions
  - SEC-U1-02: X-Content-Type-Options, X-Frame-Options, Content-Security-Policy
  - SEC-U1-03: Error responses expose exception type name only — never content or stack traces
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_logger = logging.getLogger("agent.api")


def _log_security_event(event: str, path: str) -> None:
    _logger.warning("security_event", extra={"event": event, "path": path})


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware — Pattern 3 (SEC-U1-02)
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add hardened HTTP security headers to every response.

    Headers added:
      X-Content-Type-Options: nosniff
      X-Frame-Options: DENY
      Content-Security-Policy: default-src 'none'
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response


# ---------------------------------------------------------------------------
# GlobalErrorHandlerMiddleware — Pattern 4 Layer B (SEC-U1-03)
# ---------------------------------------------------------------------------

class GlobalErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch any ASGI-level exception that bypasses FastAPI routing.

    Returns sanitized JSON: {"error": "query_failed", "message": "<ExceptionTypeName>"}
    Never includes stack traces, query content, or internal paths.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "asgi_exception",
                extra={"type": type(exc).__name__, "path": request.url.path},
            )
            return JSONResponse(
                status_code=500,
                content={"error": "query_failed", "message": type(exc).__name__},
            )
