# Evaluation Harness

## Scripts
- `run_trials.py`: local dataset trial runner (default datasets: `bookreview`, `stockmarket`).
- `run_dab_benchmark.py`: full benchmark wrapper over selected dataset set.
- `score_results.py`: computes pass@1 and writes `dab_detailed.json` + `dab_submission.json`.

## Per-Query Traceability
- `run_trials.py` writes per-query records including:
  - `query_id`
  - `pass`
  - `trace_id`
  - `tool_call_trace` (the tool calls emitted by the agent for that query/trial)
- `score_results.py` preserves trial-level `tool_call_trace` inside each `per_query` entry in `dab_detailed.json`.

## Smoke Run
```bash
python3 eval/run_trials.py --trials 2 --output results/smoke.json
python3 eval/score_results.py --results results/smoke.json
```

## Full Run
```bash
python3 eval/run_dab_benchmark.py --trials 5 --output results/dab_benchmark.json
python3 eval/score_results.py --results results/dab_benchmark.json
```
