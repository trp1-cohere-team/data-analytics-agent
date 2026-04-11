# U1 NFR Requirements Plan
# Unit 1 — Agent Core & API

**Status**: In Progress  
**Date**: 2026-04-11

---

## Unit Context

**Components**: AgentAPI, Orchestrator, ContextManager, CorrectionEngine  
**Key functional traits**: async FastAPI server, ReAct LLM loop, 3-layer context cache, tiered correction engine

---

## NFR Questions

### Performance

**Q1** — What is the target end-to-end latency for `POST /query` under normal load?

A) < 5 seconds (LLM response time dominates; DB queries are fast)  
B) < 10 seconds (acceptable for a multi-iteration ReAct loop with multiple DB calls)  
C) < 30 seconds (complex queries may need several iterations + corrections)  
D) No explicit target — best effort only  

[Answer]: C

---

**Q2** — How many concurrent `/query` requests must the server handle without degradation?

A) 1–5 (single user / small team)  
B) 5–20 (small team, occasional concurrent requests)  
C) 20–100 (department-scale usage)  
D) 100+ (production scale requiring horizontal scaling)  

[Answer]: B

---

### Reliability & Error Handling

**Q3** — What is the required behavior when the OpenRouter LLM API is fully unavailable (not just rate-limited)?

A) Return HTTP 503 immediately with `{"error": "llm_unavailable"}`  
B) Retry 3× with exponential backoff; if all fail, return HTTP 503  
C) Return a cached/fallback answer if one exists; otherwise HTTP 503  
D) Fail silently — return an empty `QueryResponse` with confidence=0.0  

[Answer]: A

---

**Q4** — What is the behavior when the MCP Toolbox (MultiDBEngine) is unavailable at `/query` time?

A) Return HTTP 503 immediately (cannot process any DB queries)  
B) Return HTTP 200 with answer="Database unavailable" and confidence=0.0  
C) Attempt the query; if all sub-queries fail, return structured error in the response body  
D) Fall back to KB-only answer (no DB data) and note it in the response  

[Answer]: C

---

### Security

**Q5** — Is authentication required for the API endpoints?

A) No authentication — the API is localhost-only / internal network only  
B) API key authentication (Bearer token in Authorization header)  
C) OAuth2 / JWT  
D) IP allowlist only  

[Answer]: A

---

**Q6** — Should the API key (`OPENROUTER_API_KEY`) be validated at startup?

A) Yes — if missing or empty, raise an error at startup and refuse to start  
B) No — allow startup without key; fail at runtime when first LLM call is made  
C) Warn at startup but proceed; LLM calls will fail gracefully at runtime  
D) Not applicable — key is always present in environment  

[Answer]: C

---

### Observability

**Q7** — What structured logging fields are required for each `/query` request?

A) `session_id`, `iterations_used`, `confidence`, `elapsed_ms` only  
B) `session_id`, `iterations_used`, `confidence`, `elapsed_ms`, `correction_count`, `action_sequence`  
C) Minimal: `session_id` and `elapsed_ms` only  
D) Full trace logging: every think/act/observe step logged at DEBUG level  

[Answer]: B

---

**Q8** — Should the Orchestrator log the question text and answer in structured logs?

A) Yes — full question and answer logged at INFO level  
B) No — only metadata logged; never log question or answer content (privacy/security)  
C) Log a truncated hash of the question only  
D) Log in development, suppress in production via log level  

[Answer]: B

---

### Tech Stack

**Q9** — Which web framework and ASGI server combination for `AgentAPI`?

A) FastAPI + Uvicorn  
B) FastAPI + Gunicorn + Uvicorn workers  
C) Starlette (raw) + Uvicorn  
D) Flask + Gevent  

[Answer]: A

---

**Q10** — How should the Orchestrator's LLM client be initialized?

A) Module-level singleton `openai.AsyncOpenAI(...)` — one client for the whole process  
B) Per-request instantiation — new client per `run()` call  
C) Injected via dependency injection into Orchestrator `__init__`  
D) Lazy singleton — initialized on first call, reused thereafter  

[Answer]: C

---

**Q11** — What testing approach for the Orchestrator's ReAct loop?

A) Unit tests with mocked LLM client (inject mock that returns controlled Thought JSON)  
B) Integration tests only — test against real OpenRouter API  
C) No tests for Orchestrator — tested end-to-end via evaluation harness  
D) Property-based tests using Hypothesis to generate random Thought sequences  

[Answer]: A

---

**Q12** — What testing approach for the CorrectionEngine?

A) Unit tests for each fix strategy function + PBT for classify_failure coverage  
B) Unit tests for each fix strategy function only (no PBT needed)  
C) Integration tests hitting a real DB with intentionally broken queries  
D) PBT only — generate random error messages and verify FailureType is always returned  

[Answer]: A

---

## Plan Steps

- [x] **Step 1** — Analyze functional design (done above)
- [x] **Step 2** — Generate `nfr-requirements.md`
- [x] **Step 3** — Generate `tech-stack-decisions.md`
- [x] **Step 4** — Update aidlc-state.md and audit.md; present completion message
