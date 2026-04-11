# Deployment Architecture
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## Runtime Architecture

```
+-------------------------------------------------+
|  Developer Machine (localhost)                  |
|                                                 |
|  +------------------------------------------+  |
|  |  Python Process (uvicorn)                |  |
|  |  agent/api/app.py  port 8000             |  |
|  |                                          |  |
|  |  [RateLimitMiddleware]                   |  |
|  |  [SecurityHeadersMiddleware]             |  |
|  |  [GlobalErrorHandlerMiddleware]          |  |
|  |                                          |  |
|  |  AgentAPI                                |  |
|  |    Orchestrator                          |  |
|  |      PromptCacheBuilder                  |  |
|  |      ExponentialBackoffRetry             |  |
|  |    ContextManager                        |  |
|  |      [Layer2RefreshTask] (asyncio)       |  |
|  |    CorrectionEngine                      |  |
|  |                                          |  |
|  |  -- imports from U2 --                   |  |
|  |  MultiDBEngine                           |  |
|  |                                          |  |
|  |  -- imports from U3 --                   |  |
|  |  KnowledgeBase                           |  |
|  |  MemoryManager                           |  |
|  |    [autoDream task] (asyncio)            |  |
|  |                                          |  |
|  |  -- imports from U5 --                   |  |
|  |  SchemaIntrospector                      |  |
|  |  MultiPassRetriever                      |  |
|  |  JoinKeyUtils                            |  |
|  +------------------------------------------+  |
|                                                 |
|  +---------------------------+                  |
|  |  MCP Toolbox  port 5000  |                  |
|  |  (separate process)      |                  |
|  +---------------------------+                  |
|                                                 |
|  +---------------------------+                  |
|  |  File System              |                  |
|  |  kb/                      |                  |
|  |  agent/memory/            |                  |
|  |  results/                 |                  |
|  +---------------------------+                  |
+-------------------------------------------------+
             |
             | HTTPS (port 443)
             v
+---------------------------+
|  OpenRouter API           |
|  api.openrouter.ai        |
|  model: openai/gpt-4o     |
+---------------------------+
```

---

## Invocation

```bash
# Start MCP Toolbox first (separate terminal)
# <toolbox start command per U2 instructions>

# Start AgentAPI
uvicorn agent.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## Data Flow Summary

| Flow | Path | Protocol |
|---|---|---|
| Client → AgentAPI | `POST localhost:8000/query` | HTTP |
| AgentAPI → Orchestrator | in-process function call | — |
| Orchestrator → OpenRouter | `POST api.openrouter.ai/v1/chat/completions` | HTTPS |
| Orchestrator → MultiDBEngine | in-process function call | — |
| MultiDBEngine → MCP Toolbox | `POST localhost:5000/api/tool/{tool_name}` | HTTP |
| ContextManager → File System | `kb/*.md`, `corrections.json` | File I/O (asyncio.to_thread) |
| MemoryManager → File System | `agent/memory/sessions/*.json`, `topics/*.json` | File I/O (asyncio.to_thread) |
| AgentAPI → MemoryManager | `save_session()` (best-effort) | in-process |
