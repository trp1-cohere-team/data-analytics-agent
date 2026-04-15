# OracleForge Data Agent

Production-grade multi-database analytics agent evaluated against the
[DataAgentBench (DAB)](https://github.com/DAB-Benchmark/DataAgentBench) benchmark.

## Architecture

```
OracleForge/
├── agent/
│   ├── AGENT.md                      # Agent identity (Layer 3 institutional knowledge)
│   ├── data_agent/
│   │   ├── types.py                  # Shared dataclasses (AgentResult, ContextPacket, ...)
│   │   ├── config.py                 # Env-driven config + offline stubs
│   │   ├── oracle_forge_agent.py     # Public facade: run_agent()
│   │   ├── execution_planner.py      # Multi-step plan builder
│   │   ├── result_synthesizer.py     # Grounded answer synthesis
│   │   ├── context_layering.py       # 6-layer context assembly
│   │   ├── knowledge_base.py         # KB retrieval (weighted ranking)
│   │   ├── failure_diagnostics.py    # 4-category failure classifier
│   │   ├── mcp_toolbox_client.py     # Unified MCP client (4 DB tools)
│   │   ├── duckdb_bridge_client.py   # Private DuckDB bridge impl
│   │   └── sandbox_client.py         # Sandbox HTTP client
│   └── runtime/
│       ├── conductor.py              # Orchestration spine
│       ├── memory.py                 # 3-layer file memory
│       ├── tooling.py                # ToolRegistry + ToolPolicy
│       └── events.py                 # Append-only JSONL event ledger
├── sandbox/
│   └── sandbox_server.py             # Flask sandbox server
├── eval/
│   ├── run_trials.py                 # Local trial runner
│   ├── run_dab_benchmark.py          # Full DAB benchmark
│   └── score_results.py             # pass@1 scorer
├── kb/
│   ├── architecture/                 # Agent architecture docs
│   ├── domain/                       # Query patterns, join-key glossary
│   ├── evaluation/                   # DAB format, scoring
│   └── corrections/corrections_log.md
├── probes/probes.md                  # 15+ adversarial probes
├── tests/                            # Unit + PBT tests
├── tools.yaml                        # MCP config (all 4 DB types)
├── requirements.txt                  # Pinned dependencies
└── .env.example                      # Environment variable template
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and DB connections
```

### 3. Run in offline mode (no API/DB needed)

```bash
AGENT_OFFLINE_MODE=1 python3 -c "
from agent.data_agent.oracle_forge_agent import run_agent
result = run_agent('How many books are there?', ['postgres'])
print(result.answer)
"
```

### 4. Run local DAB trials

```bash
AGENT_OFFLINE_MODE=1 python3 eval/run_trials.py \
  --trials 2 \
  --output results/smoke.json
```

### 5. Score results

```bash
python3 eval/score_results.py --results results/smoke.json
```

### 6. Run tests

```bash
AGENT_OFFLINE_MODE=1 python3 -m unittest discover -s tests -v
```

## Multi-Database Support

| Tool | Database | Backend |
|------|---------|---------|
| `query_postgresql` | PostgreSQL | Google MCP Toolbox |
| `query_mongodb` | MongoDB | Google MCP Toolbox |
| `query_sqlite` | SQLite | Google MCP Toolbox |
| `query_duckdb` | DuckDB | Custom MCP Bridge |

All 4 tools are configured in `tools.yaml` and accessed through the unified `MCPClient` interface.

## Sandbox Execution

Optional code sandbox for isolated Python execution:

```bash
# Start sandbox server
SANDBOX_ALLOWED_ROOTS=/tmp python3 sandbox/sandbox_server.py

# Enable sandbox in agent
AGENT_USE_SANDBOX=1 python3 eval/run_trials.py --trials 1 --output results/sandbox_test.json
```

## Server Links

| Service | Default URL | Start Command |
|---------|------------|---------------|
| Google MCP Toolbox | http://localhost:5000 | See MCP Toolbox docs |
| DuckDB Bridge | http://localhost:5001 | Custom bridge server |
| Sandbox Server | http://localhost:8080 | `python3 sandbox/sandbox_server.py` |

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Description |
|----------|-------------|
| `AGENT_OFFLINE_MODE` | `1` = offline stubs, no API calls |
| `OPENROUTER_API_KEY` | OpenRouter API key (required when offline=0) |
| `OPENROUTER_MODEL` | Model ID (default: `google/gemini-2.0-flash-001`) |
| `MCP_TOOLBOX_URL` | Google MCP Toolbox URL |
| `DUCKDB_BRIDGE_URL` | Custom DuckDB bridge URL |
| `TOOLS_YAML_PATH` | Path to `tools.yaml` |
| `AGENT_USE_SANDBOX` | `1` = enable sandbox execution |
