# U7 — Streaming API: Code Generation Plan

## Steps

- [x] Step 1: Add `StreamEvent` model to `agent/models.py`
- [x] Step 2: Add `run_stream()` async generator to `agent/orchestrator/react_loop.py`
- [x] Step 3: Add `POST /query/stream` route to `agent/api/app.py`
- [x] Step 4: Create `tests/unit/test_streaming.py`
