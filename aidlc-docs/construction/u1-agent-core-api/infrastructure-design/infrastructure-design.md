# Infrastructure Design
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## Infrastructure Summary

U1 requires no new infrastructure services. All components run in-process within a single Python `uvicorn` server. External dependencies are the OpenRouter LLM API (HTTPS) and the MCP Toolbox (localhost:5000, already mapped in U2 infrastructure design).

---

## Infrastructure Category Assessment

| Category | Decision | Rationale |
|---|---|---|
| Deployment Environment | Local Python process | Coursework/dev project; single-machine deployment |
| Compute | `uvicorn` on `localhost:8000` | Single async worker; handles 5–20 concurrent via asyncio |
| Storage | File system via U3 | KnowledgeBase + MemoryManager already own all file I/O; U1 is a pure consumer |
| Messaging | asyncio tasks (in-process) | Layer 2 refresh loop and autoDream are `asyncio.Task` objects managed in lifespan |
| Networking (inbound) | HTTP on `localhost:8000` (no TLS in dev) | Single-machine; no reverse proxy needed |
| Networking (outbound) | HTTPS to `api.openrouter.ai`; HTTP to `localhost:5000` (MCP Toolbox) | Standard outbound; `openai.AsyncOpenAI` handles TLS for OpenRouter |
| Monitoring | Python `logging` stdlib | Structured `extra={}` log entries; no external log aggregation |
| Shared | MCP Toolbox (`localhost:5000`) | Already mapped in U2 infrastructure design — no duplication |

---

## Process Ports and Bindings

| Service | Host | Port | Protocol | Direction |
|---|---|---|---|---|
| AgentAPI (Uvicorn) | localhost | 8000 | HTTP | Inbound from client / evaluation harness |
| MCP Toolbox | localhost | 5000 | HTTP | Outbound from MultiDBEngine (U2) |
| OpenRouter LLM API | api.openrouter.ai | 443 | HTTPS | Outbound from Orchestrator (U1) |

---

## Environment Variables (U1-specific)

All loaded via `agent/config.py` (`pydantic-settings`):

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | `""` | LLM API key; missing → startup WARNING, runtime HTTP 503 |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `OPENROUTER_MODEL` | `openai/gpt-4o` | Model identifier |
| `AGENT_PORT` | `8000` | Uvicorn bind port |
| `RATE_LIMIT` | `20/minute` | slowapi rate limit string |
| `MAX_REACT_ITERATIONS` | `10` | Orchestrator iteration cap |
| `CONFIDENCE_THRESHOLD` | `0.85` | Early-exit threshold |
| `MAX_CORRECTION_ATTEMPTS` | `3` | CorrectionEngine attempt cap |
| `LAYER2_REFRESH_INTERVAL_S` | `60` | ContextManager background task interval |
| `CORRECTIONS_LIMIT` | `50` | Layer 3 correction window |

---

## Startup Sequence

```
1. Load settings (pydantic-settings from .env)
2. Validate: warn if OPENROUTER_API_KEY is empty (continue)
3. Create openai.AsyncOpenAI client
4. Create KnowledgeBase, MemoryManager instances
5. KnowledgeBase.initialise() — ensure KB directory structure
6. MemoryManager.initialise() — ensure memory dirs + launch autoDream task
7. ContextManager.startup_load():
   a. SchemaIntrospector.introspect_all() → Layer 1 cache
   b. KnowledgeBase.load_documents() for each subdir → Layer 2 cache
   c. asyncio.create_task(context_manager._refresh_layer2_loop())
8. Create CorrectionEngine (injected with llm_client)
9. Create Orchestrator (injected with llm_client, engine, kb, memory)
10. Register middleware: GlobalErrorHandler, SecurityHeaders, RateLimiter
11. Uvicorn starts accepting requests on localhost:8000
```

---

## No New Infrastructure Required

U1 is a pure application layer. It produces no new storage artifacts of its own (corrections and session transcripts are owned by U3). It introduces no queue, cache service, or external database beyond what U2 and U3 already map.
