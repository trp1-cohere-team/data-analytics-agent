# Integration Test Instructions — The Oracle Forge

**Date**: 2026-04-11

---

## Overview

Integration tests verify that units work together correctly across real service boundaries. They require the full stack running: MCP Toolbox + connected databases + agent server.

Integration tests live in `tests/integration/` and are run separately from unit tests.

---

## Prerequisites

All services must be running before executing integration tests:

### 1. Start MCP Toolbox

```bash
mcp-toolbox --config tools.yaml
# Verify: curl http://localhost:5000/v1/tools
```

### 2. Start the Agent Server

```bash
# In a separate terminal
uvicorn agent.api.app:app --port 8000 --host 0.0.0.0

# Verify health
curl http://localhost:8000/health
# Expected: {"status": "ok", "mcp_toolbox": "reachable"}
```

### 3. Verify Database Connectivity

```bash
# Test each DB type via MCP Toolbox
curl -X POST http://localhost:5000/v1/tools/sqlite_query \
     -H "Content-Type: application/json" \
     -d '{"query": "SELECT 1"}'
```

---

## Integration Test Scenarios

### Scenario 1: Orchestrator ↔ MultiDBEngine ↔ MCP Toolbox

**Description**: Full query path from Orchestrator → MultiDBEngine → MCP Toolbox → DB → result.

**Test file**: `tests/integration/test_orchestrator_engine.py`

```bash
pytest tests/integration/test_orchestrator_engine.py -v
```

**Key assertions**:
- `Orchestrator.run()` returns `OrchestratorResult` with `confidence > 0`
- `MultiDBEngine.execute_plan()` correctly routes to each DB type
- MCP Toolbox responses are properly deserialized as `ExecutionResult`

---

### Scenario 2: KnowledgeBase ↔ ContextManager ↔ Orchestrator

**Description**: Layer 2 context (KB documents) reaches the Orchestrator's `think()` call.

**Test file**: `tests/integration/test_context_pipeline.py`

```bash
pytest tests/integration/test_context_pipeline.py -v
```

**Key assertions**:
- `ContextManager.get_context_bundle()` returns Layer 1 schema from live MCP Toolbox
- KB documents injected in startup_load() appear in `ContextBundle.domain_ctx`
- `ContextBundle` is passed to `Orchestrator.run()` without truncation

---

### Scenario 3: CorrectionEngine ↔ KnowledgeBase (correction logging)

**Description**: Failed queries are corrected and corrections are appended to `corrections.json`.

**Test file**: `tests/integration/test_correction_pipeline.py`

```bash
pytest tests/integration/test_correction_pipeline.py -v
```

**Key assertions**:
- `CorrectionEngine.correct()` produces a new `QueryPlan` for a known bad query
- `CorrectionEntry` appears in `kb/corrections/corrections.json` after correction
- `KnowledgeBase.get_corrections()` returns the new entry in subsequent calls

---

### Scenario 4: Full Query End-to-End via AgentAPI

**Description**: HTTP POST /query → complete ReAct loop → HTTP 200 response.

**Test file**: `tests/integration/test_e2e_query.py`

```bash
pytest tests/integration/test_e2e_query.py -v
```

**Key assertions**:
- POST `/query` with a known answerable question returns 200
- `QueryResponse.answer` is non-empty
- `QueryResponse.confidence` is in [0.0, 1.0]
- Response includes security headers (X-Content-Type-Options, X-Frame-Options, CSP)

---

### Scenario 5: MemoryManager session persistence

**Description**: Session saved after query; loaded correctly in subsequent call.

**Test file**: `tests/integration/test_memory_pipeline.py`

```bash
pytest tests/integration/test_memory_pipeline.py -v
```

**Key assertions**:
- `MemoryManager.save_session()` writes `agent/memory/sessions/{session_id}.json`
- `MemoryManager.load_session()` returns the same transcript
- Second call with same session_id raises `SessionAlreadyExists` (write-once)

---

### Scenario 6: EvaluationHarness ↔ AgentAPI (benchmark pipeline)

**Description**: Harness calls the live agent, scores answers, appends to score log.

**Test file**: `tests/integration/test_benchmark_pipeline.py`

```bash
pytest tests/integration/test_benchmark_pipeline.py -v
```

**Key assertions**:
- `EvaluationHarness.run()` completes without exception for a small DAB subset
- `results/score_log.jsonl` has one new line after the run
- `RegressionResult.passed == True` on first run (no baseline)

---

## Run All Integration Tests

```bash
pytest tests/integration/ -v --timeout=120
```

`--timeout=120` prevents hanging tests from blocking the suite indefinitely.

---

## Cleanup After Integration Tests

```bash
# Remove test sessions and traces (keep real kb/ and score_log)
rm -rf agent/memory/sessions/test-*
rm -rf results/traces/test-*

# Stop services
kill $(lsof -t -i:8000)   # agent server
kill $(lsof -t -i:5000)   # MCP Toolbox
```

---

## Troubleshooting

### `ConnectionRefusedError` on agent URL
**Fix**: Ensure `uvicorn agent.api.app:app --port 8000` is running.

### `MCP Toolbox unreachable` in health check
**Fix**: Ensure `mcp-toolbox --config tools.yaml` is running and `tools.yaml` has correct DB connection strings.

### Integration test passes in isolation but fails in suite
**Cause**: Shared state (e.g., corrections.json, session files).  
**Fix**: Each test must use a unique session_id and clean up after itself.
