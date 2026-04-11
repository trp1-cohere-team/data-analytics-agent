# The Oracle Forge — Data Analytics Agent

> TRP1 Week 8–9 Challenge: Multi-database AI agent with ReAct orchestration

---

## Team Members and Roles

| Name | Role |
|------|------|
| [TEAM MEMBER 1] | Agent Architecture & Orchestrator |
| [TEAM MEMBER 2] | Multi-DB Execution Engine & MCP Integration |
| [TEAM MEMBER 3] | Knowledge Base & Memory Management |
| [TEAM MEMBER 4] | Evaluation Harness & Benchmarking |
| [TEAM MEMBER 5] | Utilities, Probes & Signal |

---

## Architecture

The Oracle Forge is a ReAct-loop agent that queries four heterogeneous databases
(PostgreSQL, MongoDB, DuckDB, SQLite) via MCP Toolbox, with automatic failure
correction, knowledge-base-augmented context, and persistent session memory.

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI  :8000                          │
│                     POST /query  GET /health                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    Orchestrator      │  ReAct Loop (max 10 iters)
              │   (react_loop.py)    │  confidence threshold: 0.85
              └──┬──────┬──────┬────┘
                 │      │      │
        ┌────────▼─┐ ┌──▼───┐ ┌▼──────────────┐
        │ Context  │ │  KB  │ │ CorrectionEng │
        │ Manager  │ │Layer │ │  (tiered fix) │
        └────────┬─┘ └──────┘ └───────────────┘
                 │
              ┌──▼──────────────────────────────┐
              │     MultiDBEngine                │
              │   MCP Toolbox :5000              │
              └──┬──────┬──────┬──────┬──────────┘
                 │      │      │      │
            [PG] [Mongo] [Duck] [SQLite]
```

*Full architecture diagram: see `aidlc-docs/inception/application-design/`*

---

## Live Agent

**Shared server:** `http://10.0.6.41:8000`

- POST `/query` — submit a natural language question
- GET  `/health` — MCP Toolbox liveness probe
- GET  `/schema` — current schema cache

```bash
curl -X POST http://10.0.6.41:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many orders were placed last month?"}'
```

---

## Setup Instructions (Fresh Machine)

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Git

### 1. Clone the repository

```bash
git clone <repo-url>
cd data-analytics-agent
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY and database credentials
```

### 4. Start MCP stack (PostgreSQL + MongoDB + MCP Toolbox)

```bash
# Check containers
sudo docker compose -f /home/data-analytics-agent/docker-compose.mcp.yml ps

# Start if needed
sudo docker compose -f /home/data-analytics-agent/docker-compose.mcp.yml up -d
```

| Service | Port |
|---------|------|
| PostgreSQL | 5432 |
| MongoDB | 27017 |
| MCP Toolbox | 5000 |

DuckDB is local: `data/duckdb/main.duckdb` (no Docker required).

### 5. Start the agent

```bash
uvicorn agent.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Run tests

```bash
# Unit tests (373 tests, no external services needed)
python -m pytest tests/unit/ -q

# Integration tests (requires MCP Toolbox running on port 5000)
python -m pytest tests/integration/ -m integration -q
```

---

## Project Structure

```
data-analytics-agent/
├── agent/           Core agent source (API, orchestrator, engines, KB, memory)
├── kb/              Knowledge base documents (architecture, domain, evaluation, corrections)
├── eval/            Evaluation harness, score log, held-out test set
├── probes/          15 adversarial probes with standard format + runner
├── planning/        AI-DLC Inception documents + mob session approval records
├── utils/           Shared utility library (4 modules)
├── signal/          Community engagement logs and articles
├── results/         DAB benchmark results and leaderboard data
├── tests/           Unit + integration test suite (373 unit + 11 integration)
├── tools.yaml       MCP Toolbox data sources and tool definitions
└── requirements.txt Python dependencies
```
