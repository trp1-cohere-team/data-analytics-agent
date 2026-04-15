# Code Generation Plan — U4: Agent + Sandbox

## Unit Context
- **Unit**: U4 — Agent + Sandbox
- **Design Artifact**: `aidlc-docs/construction/u4-agent-sandbox/functional-design/business-logic-model.md`
- **Dependencies**: U1 (types, config), U2 (data layer), U3 (conductor, memory, tooling)
- **Workspace Root**: `/home/nurye/Desktop/TRP1/week8/OracleForge`

## Stories Implemented by This Unit
- FR-01 Agent Facade (`run_agent` public entry point, `OracleForgeAgent`)
- FR-04 Multi-step execution planning + self-correction
- FR-08 AGENT.md loaded into Layer 3 institutional knowledge
- FR-10 Optional code sandbox (AGENT_USE_SANDBOX=1)
- SEC-05 Input validation on sandbox payload
- SEC-09 Sandbox path traversal prevention
- SEC-15 Exception handling + health-check before execute

## Interfaces with Existing Code
- `OracleForgeConductor.run(question, db_hints) -> AgentResult` (conductor.py)
- `ContextPacket`, `ExecutionStep`, `FailureDiagnosis`, `ToolDescriptor`, `AgentResult` (types.py)
- Config constants: `AGENT_OFFLINE_MODE`, `AGENT_MAX_EXECUTION_STEPS`, `OFFLINE_LLM_RESPONSE`,
  `SANDBOX_URL`, `SANDBOX_TIMEOUT_SECONDS`, `SANDBOX_MAX_PAYLOAD_CHARS`,
  `SANDBOX_PY_TIMEOUT_SECONDS`, `AGENT_CONTEXT_PATH` (config.py)

---

## Steps

### Step 1: Generate `agent/data_agent/execution_planner.py`
- [x] `build_plan(question, context, tools) -> list[ExecutionStep]`
- [x] Offline stub: single-step plan with first tool
- [x] LLM path: format prompt, call OpenRouter, parse response, cap at AGENT_MAX_EXECUTION_STEPS
- [x] `propose_correction(diagnosis, context) -> str` — 4-category correction strings
- [x] Logger, input validation, SEC-03, SEC-15

### Step 2: Generate `agent/data_agent/result_synthesizer.py`
- [x] `synthesize_answer(question, evidence, context) -> tuple[str, float]`
- [x] Filter to successful evidence
- [x] No-success fallback: ("Unable to determine...", 0.1)
- [x] Offline stub path
- [x] LLM synthesis call
- [x] Confidence formula: base = successes/total, penalty = corrections*0.1, clamp [0,1]
- [x] Logger, SEC-03, SEC-15

### Step 3: Generate `agent/data_agent/oracle_forge_agent.py`
- [x] `OracleForgeAgent` class with `__init__(session_id)` and `run_agent(question, db_hints)`
- [x] Module-level `run_agent(question, db_hints)` convenience function
- [x] Thin wrapper over `OracleForgeConductor` (BR-U4-01)
- [x] No orchestration logic — delegates entirely to conductor
- [x] Logger, SEC-03

### Step 4: Generate `agent/data_agent/sandbox_client.py`
- [x] `SandboxClient` class: `__init__`, `health_check() -> bool`, `execute(code) -> dict`
- [x] Health check: GET /health before every execute (BR-U4-04)
- [x] Code length validation: <= SANDBOX_MAX_PAYLOAD_CHARS (SEC-05)
- [x] POST /execute with timeout=SANDBOX_TIMEOUT_SECONDS
- [x] Parse response: {"success": bool, "output": str, "error": str}
- [x] Failed health check returns {"success": False, "error": "sandbox_unavailable"}
- [x] Logger, try/except on all HTTP calls, SEC-15

### Step 5: Generate `sandbox/sandbox_server.py`
- [x] Flask app with GET /health and POST /execute endpoints
- [x] /health returns {"status": "ok"}
- [x] /execute: validate body, check path traversal vs SANDBOX_ALLOWED_ROOTS
- [x] Execute via subprocess with SANDBOX_PY_TIMEOUT_SECONDS timeout
- [x] Return {"success": bool, "output": str, "error": str}
- [x] Generic error messages to callers (SEC-09)
- [x] Logger, structured logging, SEC-03, SEC-09, SEC-15

### Step 6: Generate `agent/AGENT.md`
- [x] Agent name, version
- [x] Behavioral constraints (always use tools, never hallucinate data)
- [x] Operating instructions (6-layer context, self-correction, memory)
- [x] Supported databases
- [x] Output format expectations

### Step 7: Write markdown code summary
- [x] Save summary at `aidlc-docs/construction/u4-agent-sandbox/code/code-summary.md`

### Step 8: Update plan checkboxes and aidlc-state.md
- [x] Mark all steps [x]
- [x] Update aidlc-state.md current stage
