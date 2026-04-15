# Business Logic Model — U4 Agent + Sandbox

## Overview
U4 is the user-facing layer: execution planning (multi-step strategy), result synthesis (grounded answers), the public `run_agent()` facade, the sandbox execution path, and the agent identity document.

---

## Module: execution_planner.py — Multi-Step Plan Builder (FR-04)

### Responsibilities
- Build multi-step execution plans from a question + context
- Generate correction proposals when a step fails
- Uses LLM to generate plans (or offline stub)

### Public API

**`build_plan(question: str, context: ContextPacket, tools: list[ToolDescriptor]) -> list[ExecutionStep]`**

Returns an ordered list of `ExecutionStep` objects representing the agent's strategy.

**`propose_correction(diagnosis: FailureDiagnosis, context: ContextPacket) -> str`**

Returns a correction suggestion string based on the failure diagnosis.

### Algorithm: build_plan
```
1. If AGENT_OFFLINE_MODE:
   a. Return a single-step stub plan: [ExecutionStep(step_number=1, action="query", tool_name=first_tool)]
2. Format prompt with question, context summary, available tools
3. Call LLM via OpenRouter
4. Parse response into list of ExecutionStep
5. Cap at AGENT_MAX_EXECUTION_STEPS
6. Return plan
```

### Algorithm: propose_correction
```
1. Based on diagnosis.category:
   - "query": suggest syntax fix
   - "join-key": suggest schema lookup
   - "db-type": suggest tool switch
   - "data-quality": suggest data verification
2. Combine with diagnosis.suggested_fix
3. Return correction string
```

---

## Module: result_synthesizer.py — Answer Synthesis (FR-01)

### Responsibilities
- Synthesize a grounded answer from execution evidence + context
- Compute confidence score
- Format the final AgentResult

### Public API

**`synthesize_answer(question: str, evidence: list[dict], context: ContextPacket) -> tuple[str, float]`**

Returns `(answer_text, confidence)`.

### Algorithm: synthesize_answer
```
1. Filter evidence to successful results
2. If no successful results:
   a. Return ("Unable to determine the answer from the available data.", 0.1)
3. If AGENT_OFFLINE_MODE:
   a. Return (OFFLINE_LLM_RESPONSE content, 0.5)
4. Format synthesis prompt: question + successful results + context summary
5. Call LLM for synthesis
6. Compute confidence:
   a. base = successful_steps / total_steps
   b. penalty = corrections * 0.1
   c. confidence = clamp(base - penalty, 0.0, 1.0)
7. Return (synthesized_answer, confidence)
```

---

## Module: oracle_forge_agent.py — Public Facade (FR-01)

### Responsibilities
- Single public entry point: `run_agent(question, db_hints) -> AgentResult`
- Thin wrapper over `OracleForgeConductor`
- Loads AGENT.md into Layer 3 at session start (FR-08)

### Public API

**`OracleForgeAgent`** class:
- `__init__(self, session_id: str | None = None)`
- `run_agent(self, question: str, db_hints: list[str]) -> AgentResult`

**Module-level convenience function:**
- `run_agent(question: str, db_hints: list[str]) -> AgentResult`

### Algorithm: run_agent
```
1. Create OracleForgeConductor(session_id)
2. Return conductor.run(question, db_hints)
```

This is intentionally thin — all orchestration logic lives in `conductor.py`.

---

## Module: sandbox_client.py — Sandbox HTTP Client (FR-10)

### Responsibilities
- HTTP client for the sandbox server's `/execute` and `/health` endpoints
- Activated only when `AGENT_USE_SANDBOX=1`
- Health-checks server before sending payloads

### Public API

**`SandboxClient`** class:
- `__init__(self)` — reads config (SANDBOX_URL, SANDBOX_TIMEOUT_SECONDS)
- `health_check(self) -> bool` — GET /health
- `execute(self, code: str) -> dict` — POST /execute with Python code

### Algorithm: execute
```
1. Health-check first: GET {SANDBOX_URL}/health
2. If unhealthy: return {"success": False, "error": "sandbox_unavailable"}
3. Validate code length <= SANDBOX_MAX_PAYLOAD_CHARS (SEC-05)
4. POST {SANDBOX_URL}/execute with body: {"code": code, "timeout": SANDBOX_PY_TIMEOUT_SECONDS}
5. Timeout: SANDBOX_TIMEOUT_SECONDS
6. Parse response: {"success": bool, "output": str, "error": str}
7. Return result
```

---

## Module: sandbox/sandbox_server.py — Sandbox HTTP Server (FR-10)

### Responsibilities
- Flask HTTP server with `/execute` and `/health` endpoints
- Enforces `SANDBOX_ALLOWED_ROOTS` server-side
- Enforces `SANDBOX_PY_TIMEOUT_SECONDS` for code execution

### Endpoints

**`GET /health`** → `{"status": "ok"}`

**`POST /execute`**:
- Body: `{"code": str, "timeout": int (optional)}`
- Validates code doesn't access paths outside SANDBOX_ALLOWED_ROOTS
- Executes Python code in a subprocess with timeout
- Returns: `{"success": bool, "output": str, "error": str}`

### Security
- Path traversal blocked: code cannot access outside SANDBOX_ALLOWED_ROOTS
- Subprocess execution with timeout enforcement
- No network access from sandboxed code (best-effort)

---

## File: agent/AGENT.md — Agent Identity (FR-08)

### Content Structure
- Agent name and version
- Behavioral constraints (always use tools, never hallucinate data)
- Operating instructions (6-layer context, self-correction, memory)
- Supported databases (4 types via MCP)
- Output format expectations

---

## Business Rules

### BR-U4-01: Thin Facade
**Rule**: `oracle_forge_agent.py` is a thin wrapper. All orchestration logic remains in `conductor.py`.

### BR-U4-02: AGENT.MD Loaded First
**Rule**: AGENT.md is loaded into Layer 3 (institutional_knowledge) at every session start. Traced via `agent_context_loaded` event. (FR-08)

### BR-U4-03: Sandbox Opt-In
**Rule**: Sandbox is only activated when `AGENT_USE_SANDBOX=1`. When disabled, `sandbox_client.py` is never invoked. (FR-10)

### BR-U4-04: Health Before Execute
**Rule**: Sandbox client MUST health-check the server before sending payloads. Failed health check → return error without sending code.

---

## Security Compliance Summary

| Rule | Status | Rationale |
|---|---|---|
| SECURITY-03 | Compliant | All modules use logging |
| SECURITY-05 | Compliant | Sandbox validates code length; execution_planner caps steps |
| SECURITY-09 | Compliant | Sandbox server rejects path traversal; generic error messages |
| SECURITY-15 | Compliant | All HTTP calls have try/except; subprocess timeout enforced |

## PBT Compliance Summary

| Rule | Status | Rationale |
|---|---|---|
| PBT-01 | N/A | No new testable properties in U4 (orchestration layer) |
