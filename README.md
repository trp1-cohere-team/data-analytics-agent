# Oracle Forge Data Analytics Agent

Baseline implementation for TRP1 Week 8-9 challenge deliverables.

## What is implemented now
- A DAB-style agent entrypoint at `agent.data_agent.dab_interface.run_agent`.
- Claude Code-style runtime architecture under `agent/runtime/`:
  - `conductor.py`: orchestrates planning, tool execution, synthesis.
  - `worker.py`: executes planned per-database query steps.
  - `tooling.py`: explicit tool registry and policy boundaries.
  - `events.py`: durable append-only execution event log.
  - `memory.py`: explicit index/topic/session memory hierarchy.
- OpenAI-style multi-layer context pipeline:
  - Layer 1: schema + metadata context from connected databases.
  - Layer 2: institutional/domain KB retrieval (question-aware).
  - Layer 3: interaction memory (session memory + corrections log).
- OpenRouter integration with safe local fallback and trace output.
- Multi-trial evaluation runner (`eval/run_trials.py`) and scorer (`eval/score_results.py`).
- Starter Knowledge Base, planning docs, probe library, MCP tools config template.
- Utility modules and tests for join-key normalization and scoring.

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run one local query
```bash
python3 -m agent.data_agent.cli \
  "Which customer segments declined in repeat purchase and had higher support volume?" \
  --available-databases '[{"name":"sales_pg","type":"postgresql"},{"name":"support_mongo","type":"mongodb"}]' \
  --schema-info '{"sales_pg":["orders","customers"],"support_mongo":["tickets","notes"]}'
```

## Run benchmark trials
Default (sample data, 5 trials):
```bash
python3 eval/run_trials.py --trials 5 --output results/local_results_5.json
python3 eval/score_results.py --results results/local_results_5.json
```

Admin-target style run (50 trials per query):
```bash
python3 eval/run_trials.py --trials 50 --output results/local_results_50.json
python3 eval/score_results.py --results results/local_results_50.json
```

## Run DataAgentBench (real query set)
Clone DAB:
```bash
git clone --depth 1 https://github.com/ucbepic/DataAgentBench.git external/DataAgentBench
```

Smoke test on one query:
```bash
python3 eval/run_dab_benchmark.py \
  --dab-root external/DataAgentBench \
  --datasets bookreview \
  --query-limit 1 \
  --trials 2 \
  --output-detailed results/dab_smoke_detailed.json \
  --output-submission results/dab_smoke_submission.json
```

Full benchmark (54 queries x 50 runs):
```bash
python3 eval/run_dab_benchmark.py \
  --dab-root external/DataAgentBench \
  --trials 50 \
  --output-detailed results/dab_full_50_detailed.json \
  --output-submission results/dab_full_50_submission.json
```

## Run tests
```bash
python3 -m unittest discover -s tests -v
```

## OpenRouter mode
By default the agent runs in offline mode for local reproducibility.

Set these in `.env` to enable live model calls:
```bash
AGENT_OFFLINE_MODE=0
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4.1-mini
AGENT_USE_MCP=1
MCP_TOOLBOX_URL=http://localhost:5000
AGENT_MEMORY_ROOT=.oracle_forge_memory
AGENT_RUNTIME_EVENTS_PATH=.oracle_forge_memory/events.jsonl
AGENT_CORRECTIONS_LOG_PATH=kb/corrections/corrections_log.md
AGENT_CONTEXT_PATH=agent/AGENT.md
```

## Project structure
- `agent/`: agent code, `AGENT.md`, and context contract.
- `eval/`: benchmark runner, scorer, held-out sample.
- `kb/`: architecture/domain/evaluation/corrections knowledge layers.
- `probes/`: adversarial probes.
- `planning/`: AI-DLC playbook, team operating roadmap, inception, operations notes, and phase templates.
- `signal/`: communication and community engagement logs.
- `utils/`: reusable helpers.
- `mcp/tools.yaml`: MCP toolbox config template for 4 DB types.
- `results/`: benchmark outputs and submission artifacts.
