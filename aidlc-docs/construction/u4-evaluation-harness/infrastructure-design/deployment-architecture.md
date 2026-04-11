# Deployment Architecture — U4 Evaluation Harness

**Unit**: U4 — Evaluation Harness  
**Date**: 2026-04-11

---

## Deployment Model

U4 is deployed as a CLI script within the same Python environment as the agent. There is no separate process, container, or service to deploy for U4 itself.

```
Developer Workstation / CI Runner
  |
  +-- [Process 1] Agent server (U1)
  |     python -m uvicorn agent.api.app:app --port 8000
  |     (must be running before benchmark starts)
  |
  +-- [Process 2] MCP Toolbox (U2 dependency)
  |     ./mcp-toolbox --config tools.yaml
  |     (must be running before benchmark starts)
  |
  +-- [Process 3] Evaluation Harness (U4) — one-off
        python -m eval.run_benchmark \
          --agent-url http://localhost:8000 \
          --trials 1 \
          --category NUMERIC
        (exits after run; writes results/ and exits 0 or 1)
```

---

## Execution Prerequisites

Before running `eval.run_benchmark`:
1. Agent server (U1) must be listening on `--agent-url`
2. MCP Toolbox must be running (agent depends on it)
3. `OPENROUTER_API_KEY` must be set in environment (for LLM judge)
4. DAB query files must exist in `--queries-path` (default: `signal/`)

---

## Output Artifacts

All output is written to the local filesystem under `results/`:

```
results/
  score_log.jsonl          ← append-only; one JSON line per run
  traces/
    {run_id}/
      {query_id}_trial_0.json
      {query_id}_trial_1.json
      ...
```

`results/` is created automatically if it does not exist.

---

## CI Integration

```yaml
# Example CI step
- name: Run regression benchmark
  run: |
    python -m eval.run_benchmark \
      --agent-url http://localhost:8000 \
      --trials 1
  # Non-zero exit if regression detected (BR-U4-16)
```

Exit code `1` fails the CI job automatically when `RegressionResult.passed == False`.
