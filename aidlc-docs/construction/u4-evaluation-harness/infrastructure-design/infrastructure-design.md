# Infrastructure Design — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Assessment Summary

U4 introduces no standalone infrastructure. It is a batch CLI tool that runs as a one-off Python process within the same environment as the agent server.

| Category | Status | Rationale |
|---|---|---|
| Deployment Environment | N/A | Local Python process; no container, no cloud service |
| Compute Infrastructure | N/A | No persistent compute; executes and exits |
| Storage Infrastructure | N/A | Local filesystem (`results/`) — no database, no object storage |
| Messaging Infrastructure | N/A | asyncio in-process concurrency; no external queues |
| Networking Infrastructure | N/A | HTTP client only; no ingress, no load balancer |
| Monitoring Infrastructure | N/A | Structured stdout logging; no APM or external sink |
| Shared Infrastructure | N/A | Reuses `OPENROUTER_API_KEY` from env — no new shared services |

---

## Runtime Dependencies (Not Infrastructure)

These are runtime targets U4 calls but does not own or provision:

| Target | Type | Owned by |
|---|---|---|
| Agent server (`http://localhost:8000`) | HTTP endpoint | U1 — AgentAPI |
| OpenRouter API | External LLM API | Third-party (shared key from env) |
| `results/` directory | Local filesystem | Created by U4 at runtime (`mkdir parents=True, exist_ok=True`) |

---

## No New Infrastructure

No `infrastructure-design.md` changes to the shared infrastructure document are required. U4 does not add, modify, or depend on any provisioned cloud or on-premise services.
