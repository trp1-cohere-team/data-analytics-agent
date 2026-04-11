"""FastAPI application factory for The Oracle Forge agent.

Design decisions:
  - Pattern 5: StructuredRequestLogger — 6 metadata fields; no content
  - Pattern 4: DualLayerErrorHandler — @exception_handler(Exception) Layer A
  - Pattern 7: LifespanManagedTasks — asyncio.create_task in lifespan context manager
  - BR-U1-02: caller-supplied session_id accepted as-is (Q11=B)
  - BR-U1-14: save_session called after OrchestratorResult, best-effort (Q8=A)
  - BR-U1-15: never expose stack traces in error responses (SEC-U1-03)
  - NFR-U1-S2: missing OPENROUTER_API_KEY → startup WARNING only (Q6=C)
"""
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent.config import settings
from agent.execution.mcp_client import probe_mcp_toolbox
from agent.models import HealthResponse, QueryRequest, QueryResponse, SchemaResponse

_logger = logging.getLogger("agent.api")

# ---------------------------------------------------------------------------
# Rate limiter (slowapi)
# ---------------------------------------------------------------------------

_limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Module-level references (populated by lifespan)
# ---------------------------------------------------------------------------

_orchestrator: Any = None
_context_manager: Any = None
_memory_manager: Any = None
_kb: Any = None

# ---------------------------------------------------------------------------
# Structured logger — Pattern 5 (SEC-U1-01)
# ---------------------------------------------------------------------------

def _log_request_complete(
    session_id: str,
    iterations_used: int,
    confidence: float,
    elapsed_ms: float,
    correction_count: int,
    action_sequence: list[str],
) -> None:
    _logger.info("request_complete", extra={
        "session_id": session_id,
        "iterations_used": iterations_used,
        "confidence": round(confidence, 4),
        "elapsed_ms": round(elapsed_ms, 1),
        "correction_count": correction_count,
        "action_sequence": action_sequence,
    })

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from agent.api.middleware import GlobalErrorHandlerMiddleware, SecurityHeadersMiddleware

    app = FastAPI(
        title="The Oracle Forge — Data Analytics Agent",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware stack (applied last-to-first — GlobalError wraps everything)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GlobalErrorHandlerMiddleware)

    # Rate limiter state
    app.state.limiter = _limiter

    # Routes
    app.add_api_route("/query", handle_query, methods=["POST"], response_model=QueryResponse)
    app.add_api_route("/health", health_check, methods=["GET"], response_model=HealthResponse)
    app.add_api_route("/schema", get_schema_info, methods=["GET"], response_model=SchemaResponse)

    # Layer A error handler — Pattern 4 (SEC-U1-03)
    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _logger.error("unhandled_exception", extra={
            "type": type(exc).__name__,
            "path": request.url.path,
        })
        return JSONResponse(
            status_code=500,
            content={"error": "query_failed", "message": type(exc).__name__},
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})

    return app

# ---------------------------------------------------------------------------
# Lifespan — Pattern 7: LifespanManagedTasks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise all components, launch background tasks.
    Shutdown: cancel background tasks cleanly.
    """
    global _orchestrator, _context_manager, _memory_manager, _kb

    import openai

    from agent.context.manager import ContextManager
    from agent.correction.engine import CorrectionEngine
    from agent.execution.engine import MultiDBEngine
    from agent.execution.mcp_client import AiohttpMCPClient
    from agent.kb.knowledge_base import KnowledgeBase
    from agent.memory.manager import MemoryManager
    from agent.orchestrator.react_loop import Orchestrator
    from utils.multi_pass_retriever import MultiPassRetriever
    from utils.schema_introspector import SchemaIntrospector

    # Warn on missing API key (NFR-U1-S2 / Q6=C)
    if not settings.openrouter_api_key:
        _logger.warning("openrouter_api_key_missing — LLM calls will fail at runtime")

    # LLM client
    llm_client = openai.AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key or "missing",
    )

    # U3: KB + Memory
    _kb = KnowledgeBase(kb_dir=settings.kb_dir)
    await _kb.initialise()

    _memory_manager = MemoryManager(
        memory_dir=settings.memory_dir,
        autodream_poll_s=300,
    )
    await _memory_manager.initialise()

    # U5: SchemaIntrospector
    introspector = SchemaIntrospector(base_url=str(settings.mcp_toolbox_url))
    retriever = MultiPassRetriever()

    # Context manager
    _context_manager = ContextManager(
        kb=_kb,
        memory=_memory_manager,
        schema_introspector=introspector,
    )
    await _context_manager.startup_load()
    refresh_task = asyncio.create_task(_context_manager._refresh_layer2_loop())

    # U2: MultiDBEngine
    async with AiohttpMCPClient(base_url=str(settings.mcp_toolbox_url)) as mcp_client:
        engine = MultiDBEngine(
            mcp_client=mcp_client,
            per_query_row_cap=settings.max_result_rows,
            merge_row_cap=settings.max_result_rows,
        )

        correction_engine = CorrectionEngine(llm_client=llm_client, engine=engine)

        _orchestrator = Orchestrator(
            llm_client=llm_client,
            engine=engine,
            kb=_kb,
            memory=_memory_manager,
            retriever=retriever,
            correction_engine=correction_engine,
        )

        yield  # Server runs here

    # Shutdown
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@_limiter.limit(settings.rate_limit)
async def handle_query(request: Request, body: QueryRequest) -> QueryResponse:
    """POST /query — main entry point (BR-U1-01, BR-U1-02, BR-U1-14)."""
    t0 = time.monotonic()

    # Resolve session_id (Q11=B: use caller-supplied or generate)
    session_id = body.session_id or str(uuid.uuid4())

    # Assemble context
    context = await _context_manager.get_context_bundle(session_id)

    # Run orchestrator
    result = await _orchestrator.run(
        query=body.question,
        session_id=session_id,
        context=context,
        max_iterations=settings.max_react_iterations,
        confidence_threshold=settings.confidence_threshold,
    )

    # Save session — best-effort (BR-U1-14, Q8=A)
    summary = f"Q: {body.question[:200]} A: {str(result.answer)[:200]}"
    try:
        await _memory_manager.save_session(session_id, result.query_trace, summary)
    except Exception:  # noqa: BLE001
        _logger.warning("save_session_failed", extra={"session_id": session_id})

    # Extract action sequence and correction count from trace
    action_sequence = [step.action for step in result.query_trace]
    correction_count = sum(1 for a in action_sequence if "correct" in a.lower())

    elapsed_ms = (time.monotonic() - t0) * 1000
    _log_request_complete(
        session_id=session_id,
        iterations_used=result.iterations_used,
        confidence=result.confidence,
        elapsed_ms=elapsed_ms,
        correction_count=correction_count,
        action_sequence=action_sequence,
    )

    return QueryResponse(
        answer=result.answer,
        query_trace=result.query_trace,
        confidence=result.confidence,
        session_id=session_id,
    )


async def health_check() -> HealthResponse:
    """GET /health — MCP Toolbox reachability probe."""
    import aiohttp

    mcp_ok = False
    async with aiohttp.ClientSession() as session:
        try:
            await probe_mcp_toolbox(session, str(settings.mcp_toolbox_url))
            mcp_ok = True
        except Exception:  # noqa: BLE001
            pass

    return HealthResponse(
        status="ok" if mcp_ok else "degraded",
        mcp_toolbox=mcp_ok,
    )


async def get_schema_info() -> SchemaResponse:
    """GET /schema — returns Layer 1 schema from ContextManager cache."""
    if _context_manager is None:
        return SchemaResponse(databases={})
    bundle = _context_manager._schema_ctx
    if bundle is None:
        return SchemaResponse(databases={})
    return SchemaResponse(
        databases={
            name: {"tables": [t.name for t in db.tables]}
            for name, db in bundle.databases.items()
        }
    )


# ---------------------------------------------------------------------------
# WSGI entry point
# ---------------------------------------------------------------------------

app = create_app()
