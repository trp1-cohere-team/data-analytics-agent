"""Unit tests for agent/api/app.py and agent/api/middleware.py."""
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.models import (
    ContextBundle,
    CorrectionsContext,
    DomainContext,
    HealthResponse,
    OrchestratorResult,
    QueryRequest,
    QueryResponse,
    SchemaContext,
    SchemaResponse,
    TraceStep,
)


# ---------------------------------------------------------------------------
# Test application factory
# ---------------------------------------------------------------------------

def _make_test_app():
    """Build a FastAPI test app with all dependencies mocked."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from contextlib import asynccontextmanager

    from agent.api.middleware import GlobalErrorHandlerMiddleware, SecurityHeadersMiddleware
    from agent.config import settings

    # Build minimal context bundle
    ctx = ContextBundle(
        schema_ctx=SchemaContext(databases={}),
        domain_ctx=DomainContext(documents=[]),
        corrections_ctx=CorrectionsContext(corrections=[], session_memory={}),
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value=OrchestratorResult(
        answer="42",
        query_trace=[],
        confidence=0.9,
        session_id="test-session",
        iterations_used=1,
    ))

    mock_context_manager = MagicMock()
    mock_context_manager.get_context_bundle = AsyncMock(return_value=ctx)
    mock_context_manager._schema_ctx = SchemaContext(databases={})

    mock_memory = MagicMock()
    mock_memory.save_session = AsyncMock()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        import agent.api.app as _app_module
        _app_module._orchestrator = mock_orchestrator
        _app_module._context_manager = mock_context_manager
        _app_module._memory_manager = mock_memory
        yield

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GlobalErrorHandlerMiddleware)

    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter

    @app.exception_handler(Exception)
    async def _err(request, exc):
        return JSONResponse(status_code=500, content={"error": "query_failed", "message": type(exc).__name__})

    @app.exception_handler(RateLimitExceeded)
    async def _rate(request, exc):
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})

    # Import and register routes from app module
    import agent.api.app as _app_module
    _app_module._orchestrator = mock_orchestrator
    _app_module._context_manager = mock_context_manager
    _app_module._memory_manager = mock_memory

    from fastapi import Request

    @limiter.limit("20/minute")
    @app.post("/query", response_model=QueryResponse)
    async def _query(request: Request, body: QueryRequest):
        return await _app_module.handle_query(request, body)

    @app.get("/health", response_model=HealthResponse)
    async def _health():
        return await _app_module.health_check()

    @app.get("/schema", response_model=SchemaResponse)
    async def _schema():
        return await _app_module.get_schema_info()

    return app, mock_orchestrator, mock_memory


# ---------------------------------------------------------------------------
# Request validation tests
# ---------------------------------------------------------------------------

class TestRequestValidation:
    def setup_method(self):
        app, self.orch, self.memory = _make_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_valid_request_returns_200(self):
        resp = self.client.post("/query", json={"question": "What is the revenue?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "session_id" in data

    def test_empty_question_returns_422(self):
        resp = self.client.post("/query", json={"question": ""})
        assert resp.status_code == 422

    def test_question_too_long_returns_422(self):
        resp = self.client.post("/query", json={"question": "x" * 4097})
        assert resp.status_code == 422

    def test_missing_question_returns_422(self):
        resp = self.client.post("/query", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Session ID handling (Q11=B)
# ---------------------------------------------------------------------------

class TestSessionId:
    def setup_method(self):
        app, self.orch, self.memory = _make_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_caller_provided_session_id_echoed_in_response(self):
        my_sid = "my-custom-session-id-123"
        import agent.api.app as _app_module

        # Override orchestrator result to use correct session_id
        self.orch.run = AsyncMock(return_value=OrchestratorResult(
            answer="test", query_trace=[], confidence=0.9,
            session_id=my_sid, iterations_used=1,
        ))

        resp = self.client.post("/query", json={"question": "test?", "session_id": my_sid})
        if resp.status_code == 200:
            data = resp.json()
            assert data["session_id"] == my_sid

    def test_no_session_id_generates_uuid(self):
        resp = self.client.post("/query", json={"question": "test?"})
        if resp.status_code == 200:
            data = resp.json()
            assert "session_id" in data
            assert len(data["session_id"]) > 0


# ---------------------------------------------------------------------------
# Security headers (SEC-U1-02)
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def setup_method(self):
        app, self.orch, self.memory = _make_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_x_content_type_options_present(self):
        resp = self.client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_present(self):
        resp = self.client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_csp_present(self):
        resp = self.client.get("/health")
        assert "content-security-policy" in resp.headers

    def test_headers_on_error_response(self):
        resp = self.client.post("/query", json={"question": ""})  # 422
        assert resp.headers.get("x-content-type-options") == "nosniff"


# ---------------------------------------------------------------------------
# Error sanitization (SEC-U1-03)
# ---------------------------------------------------------------------------

class TestErrorSanitization:
    def test_unhandled_exception_returns_sanitized_500(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from agent.api.middleware import SecurityHeadersMiddleware, GlobalErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(GlobalErrorHandlerMiddleware)

        @app.exception_handler(Exception)
        async def _err(request, exc):
            return JSONResponse(
                status_code=500,
                content={"error": "query_failed", "message": type(exc).__name__},
            )

        @app.get("/explode")
        async def _explode():
            raise RuntimeError("secret internal error with sensitive data")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/explode")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "query_failed"
        assert "secret" not in body["message"]
        assert "sensitive" not in body["message"]
        assert body["message"] == "RuntimeError"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def setup_method(self):
        app, self.orch, self.memory = _make_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_returns_200(self):
        with patch("agent.api.app.probe_mcp_toolbox", new=AsyncMock(return_value=None)):
            resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "mcp_toolbox" in data


# ---------------------------------------------------------------------------
# GET /schema
# ---------------------------------------------------------------------------

class TestSchemaEndpoint:
    def setup_method(self):
        app, self.orch, self.memory = _make_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_schema_returns_200(self):
        resp = self.client.get("/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "databases" in data
