# U6 — Code Sandbox: Code Generation Plan

## Steps

- [x] Step 1: Add `SandboxResult` model to `agent/models.py`
- [x] Step 2: Create `agent/execution/sandbox.py` — `CodeSandbox` class
- [x] Step 3: Add `transform_data` action to `agent/orchestrator/react_loop.py`
- [x] Step 4: Wire `CodeSandbox` into `agent/api/app.py` lifespan
- [x] Step 5: Add sandbox action to system prompt in orchestrator
- [x] Step 6: Create `tests/unit/test_sandbox.py`
