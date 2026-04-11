# Oracle Forge Data Analytics Agent

Baseline implementation for TRP1 Week 8-9 challenge deliverables.

## Team Members and Roles
- Drivers: Nurye, Kemerya
- Intelligence Officers: Amare, Ephrata
- Signal Corps: Yohanis, Addisu

## Ownership Split
- Nurye (Driver): Agent runtime quality, routing and self-correction fixes, technical sign-off for gates.
- Kemerya (Driver): Shared server reliability, benchmark run operations, final submission packaging checks.
- Amare (Intelligence Officer): KB architecture/evaluation updates, probe failure taxonomy, weekly ecosystem brief.
- Ephrata (Intelligence Officer): KB domain/corrections updates, injection-test evidence, failure-to-fix loop with Drivers.
- Yohanis (Signal Corps): Daily internal update posts, X thread drafting and scheduling, technical milestone communication.
- Addisu (Signal Corps): Community participation log, long-form article publishing, final engagement portfolio and metrics.

## What is implemented now
- A DAB-style agent entrypoint at `agent.data_agent.dab_interface.run_agent`.
- Claude Code-style runtime architecture under `agent/runtime/`:
  - `conductor.py`: orchestrates planning, tool execution, synthesis.
  - `worker.py`: executes planned per-database query steps.
  - `tooling.py`: explicit tool registry and policy boundaries.
  - `events.py`: durable append-only execution event log.
  - `memory.py`: explicit index/topic/session memory hierarchy.
- OpenAI-style 6-layer context pipeline:
  - Layer 1: table usage (connected DBs + schema inventory + join-key hints).
  - Layer 2: human annotations (question-aware retrieval from `kb/domain`).
  - Layer 3: codex enrichment (question-aware code retrieval from agent/runtime/utils files).
  - Layer 4: institutional knowledge (`agent/AGENT.md` + `kb/architecture` + `kb/evaluation`).
  - Layer 5: interaction memory (session memory + corrections log).
  - Layer 6: runtime context (routes, selected DBs, discovered tools, execution mode).
- Automatic memory learnings extraction + topic distillation to keep long-running sessions useful.
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

Pull real dataset files (required; DAB uses Git LFS):
```bash
# if command not found: sudo apt-get update && sudo apt-get install -y git-lfs
git lfs install
cd external/DataAgentBench
git lfs pull
# required by DAB for PATENTS dataset:
bash download.sh
cd ../..
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

Note: `eval/run_dab_benchmark.py` now disables MCP by default (`AGENT_USE_MCP=0`) so DAB queries run against each query's local DB artifacts (`.db` / `.sql`). Use `--allow-mcp` only if you intentionally want toolbox-backed execution.

Full benchmark (54 queries x 50 runs):
```bash
python3 eval/run_dab_benchmark.py \
  --dab-root external/DataAgentBench \
  --trials 50 \
  --output-detailed results/dab_full_50_detailed.json \
  --output-submission results/dab_full_50_submission.json
```

If `total_valid_runs` is `0`, check these first:
- `AGENT_OFFLINE_MODE` is `0` and `OPENROUTER_API_KEY` is set (offline mode only returns fallback summaries and usually scores `0`).
- DAB files are not Git LFS pointers (`git lfs pull` completed successfully).
- You did not force `--allow-mcp` by mistake for DAB runs.
- If you see errors like `relation "public.*" does not exist`, rerun with default local mode (no `--allow-mcp`).

## Run tests
```bash
python3 -m unittest discover -s tests -v
```

## Docker setup for all 4 DB types
Run PostgreSQL + MongoDB + MCP toolbox in Docker, and keep SQLite as a local file mounted into the toolbox container.

Note: MCP Toolbox `v0.30.0` does not expose a DuckDB source type. This project executes DuckDB through the local Python `duckdb` driver (`DUCKDB_PATH`) while PostgreSQL/SQLite/MongoDB run through toolbox tools.

Start services:
```bash
mkdir -p data/sqlite data/duckdb
docker compose --env-file .env.example up -d
```

Verify toolbox tools:
```bash
curl -sS -X POST http://localhost:5000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -m json.tool
```

If image pull fails with `error from registry: denied`, reset Docker auth and retry:
```bash
docker logout
docker logout ghcr.io || true
docker logout us-central1-docker.pkg.dev || true
docker pull docker.io/library/postgres:16
docker pull docker.io/library/mongo:7
docker pull us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:0.30.0
docker compose --env-file .env.example up -d
```

Agent runtime `.env` minimum:
```bash
AGENT_USE_MCP=1
MCP_TOOLBOX_URL=http://localhost:5000
AGENT_OFFLINE_MODE=1
DUCKDB_PATH=./data/duckdb/main.duckdb
```

Install Python dependencies inside your virtualenv (required for DuckDB local execution):
```bash
.venv/bin/pip install -r requirements.txt
```

Docker files used:
- `docker-compose.yml`
- `mcp/tools.docker.yaml`

## EC2 implementation runbook
Validated setup pattern for the team EC2 server:
- Run PostgreSQL + MongoDB + MCP toolbox on EC2 with Docker Compose.
- Use DuckDB locally on EC2 through Python (`duckdb` package + `DUCKDB_PATH`).
- No Docker Desktop is needed on EC2 (Linux server).

If Docker permission is denied for non-root user:
```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# reconnect SSH (or run: newgrp docker)
```

Start/stop/status (replace compose file if you use a custom one such as `docker-compose.mcp.yml`):
```bash
COMPOSE_FILE=/home/data-analytics-agent/docker-compose.yml

# start
sudo docker compose -f "$COMPOSE_FILE" up -d

# status
sudo docker compose -f "$COMPOSE_FILE" ps

# stop (keep containers)
sudo docker compose -f "$COMPOSE_FILE" stop

# stop and remove containers/network
sudo docker compose -f "$COMPOSE_FILE" down
```

Health check MCP tools:
```bash
curl -sS -X POST http://localhost:5000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -m json.tool
```

Expected database model on EC2:
- MCP toolbox tools: PostgreSQL + SQLite + MongoDB.
- DuckDB: local Python driver (not MCP toolbox in this `v0.30.0` setup).

Verify DuckDB quickly:
```bash
python -m pip install duckdb
python - <<'PY'
import duckdb, os
p = "/home/data-analytics-agent/data/duckdb/main.duckdb"
os.makedirs(os.path.dirname(p), exist_ok=True)
con = duckdb.connect(p)
print(con.execute("select 1 as ok").fetchall())
PY
```

Team operation tip:
- Only one teammate needs to run `up -d` when services are down.
- Everyone else can check status with `docker compose ... ps`.

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
- `mcp/tools.docker.yaml`: Docker-targeted toolbox config for 4 DB types.
- `docker-compose.yml`: local Postgres + MongoDB + MCP toolbox stack.
- `results/`: benchmark outputs and submission artifacts.
