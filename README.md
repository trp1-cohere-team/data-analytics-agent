# OracleForge Data Analytics Agent

Production-grade multi-database analytics agent for the TRP1 Oracle Forge challenge.  
Answers natural-language data questions by routing queries across PostgreSQL, MongoDB, SQLite, and DuckDB through a unified MCP tool interface.

## Team Roster and Roles
- Drivers: Nurye, Kemerya
- Intelligence Officers: Amare, Ephrata
- Signal Corps: Yohanis, Addisu

## Live Agent Access (Shared Server)
- Public live endpoint: `https://oracle-forge-sandbox.yohannesdereje1221.workers.dev/`
- Shared-server health endpoint: `http://YOUR_SHARED_SERVER_HOST:8080/health`
- Query endpoint (CLI over SSH on shared host):
  - `python3 -m agent.data_agent.cli "What was the maximum adjusted closing price in 2020 for The RealReal, Inc.?" --db-hints '["sqlite","duckdb"]'`

Replace `YOUR_SHARED_SERVER_HOST` with your team's shared-server host/IP before final submission (public endpoint above is already live).

---

## End-to-End Architecture

```mermaid
flowchart TD
    U(["👤 User / Facilitator\nNatural-language question + db-hints"])

    subgraph ENTRY["Entry Points"]
        CLI["🖥️ CLI\nagent/data_agent/cli.py"]
        DAB["📊 DAB Interface\nagent/data_agent/dab_interface.py\nrun_agent(question, dbs, schema_info)"]
    end

    subgraph FACADE["Public Facade"]
        OFA["🔮 OracleForge Agent\nagent/data_agent/oracle_forge_agent.py\n• Validates input & resolves db-hints\n• Assigns trace_id\n• Returns AgentResult"]
    end

    subgraph RUNTIME["Runtime Orchestration — agent/runtime/conductor.py"]
        CTX["📋 6-Layer Context Assembly\nL6 User question\nL5 Session memory\nL4 Runtime context\nL3 Institutional KB\nL2 Domain hints\nL1 Schema & tables"]
        PLAN["🗺️ Execution Planner\nagent/data_agent/execution_planner.py\nMulti-step plan · self-correction retries"]
        MEM["🧠 Memory Manager\nagent/runtime/memory.py\n3-layer file store · 12-turn sessions"]
        KB["📚 Knowledge Base\nagent/data_agent/knowledge_base.py\nkb/architecture · kb/domain\nkb/evaluation · kb/corrections"]
        SYNTH["⚗️ Result Synthesizer\nagent/data_agent/result_synthesizer.py\nMerge evidence · confidence score 0–1"]
        EVT["📝 Event Ledger\nagent/runtime/events.py\n.oracle_forge_memory/events.jsonl"]
    end

    subgraph TOOLS["Tool Layer — read-only  •  agent/data_agent/tooling.py + ToolPolicy"]
        MCP["🔧 MCP Toolbox Client\nagent/data_agent/mcp_toolbox_client.py\nHTTP → :5000"]
        DDB["🦆 DuckDB Bridge Client\nagent/data_agent/duckdb_bridge_client.py\nHTTP → :5001"]
        SBX["📦 Sandbox Client\nagent/data_agent/sandbox_client.py\nHTTP → :8080  (AGENT_USE_SANDBOX=1)"]
    end

    subgraph DOCKER["Docker Infrastructure — docker-compose.yml"]
        TOOLBOX["⚙️ Google MCP Toolbox\noracle_forge_mcp_toolbox\n:5000"]
        BRIDGE["🌉 DuckDB Bridge Server\nsandbox/local_db_server.py\noracle_forge_duckdb_bridge\n:5001"]
        SANDBOX["🏖️ Sandbox Server\nsandbox/sandbox_server.py\noracle_forge_sandbox\n:8080"]
    end

    subgraph DBS["Databases"]
        PG[("🐘 PostgreSQL\noracle_forge_postgres\n:5432\nDAB retail & CRM datasets")]
        MONGO[("🍃 MongoDB\noracle_forge_mongo\n:27017\nDAB document datasets")]
        SQLITE[("📁 SQLite\ndata/sqlite/main.db\nStock metadata · stockinfo table")]
        DUCKDB[("🦆 DuckDB\ndata/duckdb/main.duckdb\nStock OHLCV · one table per ticker")]
    end

    subgraph EVAL["Evaluation"]
        HARNESS["📐 Eval Harness\neval/run_dab_benchmark.py\neval/run_trials.py"]
        RESULTS["📈 Results\nresults/dab_detailed.json\nresults/dab_submission.json"]
        SCRIPTS["🔄 Data Loading\nscripts/load_dab_datasets.py\nscripts/load_postgres_mongo.py\nscripts/load_remaining.py"]
    end

    U --> CLI
    U --> DAB
    CLI --> OFA
    DAB --> OFA

    OFA --> CTX
    CTX --> MEM
    CTX --> KB
    CTX --> PLAN
    PLAN --> TOOLS
    PLAN --> SYNTH
    SYNTH --> EVT
    SYNTH --> OFA

    MCP --> TOOLBOX
    DDB --> BRIDGE
    SBX --> SANDBOX

    TOOLBOX --> PG
    TOOLBOX --> MONGO
    TOOLBOX --> SQLITE
    BRIDGE --> DUCKDB

    HARNESS --> OFA
    HARNESS --> RESULTS
    SCRIPTS --> PG
    SCRIPTS --> MONGO
    SCRIPTS --> SQLITE
    SCRIPTS --> DUCKDB

    style ENTRY fill:#e8f4f8,stroke:#2196F3
    style FACADE fill:#e8f5e9,stroke:#4CAF50
    style RUNTIME fill:#fff3e0,stroke:#FF9800
    style TOOLS fill:#f3e5f5,stroke:#9C27B0
    style DOCKER fill:#fce4ec,stroke:#E91E63
    style DBS fill:#e0f2f1,stroke:#009688
    style EVAL fill:#f5f5f5,stroke:#607D8B
```

### Database Routing

| Question Domain | Tool | Database | Key Tables |
|----------------|------|----------|-----------|
| Stock prices, OHLCV, volume, Adj Close | `query_duckdb` | DuckDB | One table per ticker (e.g. `AAPL`, `MSFT`) |
| Stock metadata, company names, exchange | `query_sqlite` | SQLite | `stockinfo` |
| Retail, CRM, and other DAB datasets | `query_postgresql` | PostgreSQL | DAB-loaded tables |
| Document-store DAB datasets | `query_mongodb` | MongoDB | DAB collections |

### Operational Modes

| Env Var | Effect |
|---------|--------|
| `AGENT_USE_MCP=1` | Use live MCP tools (default) |
| `AGENT_USE_SANDBOX=1` | Route code execution through sandbox server |
| `AGENT_OFFLINE_MODE=1` | Stub LLM — no API calls, deterministic output |

---

## Architecture (Component Map)
- Public facade: `agent/data_agent/oracle_forge_agent.py`
- Runtime orchestration: `agent/runtime/conductor.py`
- Unified DB client: `agent/data_agent/mcp_toolbox_client.py`
- DuckDB bridge client: `agent/data_agent/duckdb_bridge_client.py`
- Context layering + KB retrieval: `agent/data_agent/context_layering.py`, `agent/data_agent/knowledge_base.py`
- Execution planning + failure diagnostics: `agent/data_agent/execution_planner.py`, `agent/data_agent/failure_diagnostics.py`
- Result synthesis: `agent/data_agent/result_synthesizer.py`
- Memory + event ledger: `agent/runtime/memory.py`, `agent/runtime/events.py`
- Optional sandbox execution path: `agent/data_agent/sandbox_client.py`, `sandbox/sandbox_server.py`
- DuckDB bridge server: `sandbox/local_db_server.py`
- Data loading scripts: `scripts/load_dab_datasets.py`, `scripts/load_postgres_mongo.py`, `scripts/load_remaining.py`

## Clean-Machine Setup (Facilitator Runbook)
1. Clone the repository.
```bash
git clone <repo-url>
cd data-analytics-agent
```
2. Create and activate Python environment.
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
3. Copy environment template.
```bash
cp .env.example .env
```
4. Start local infra stack.
```bash
docker compose -f docker-compose.yml up -d
./scripts/healthcheck_stack.sh
```
5. Run one agent query end-to-end.
```bash
python3 -m agent.data_agent.cli \
  "What was the maximum adjusted closing price in 2020 for The RealReal, Inc.?" \
  --db-hints '["sqlite","duckdb"]'
```
6. Run tests.
```bash
python3 -m unittest discover -s tests -v
```
7. Run evaluation harness baseline.
```bash
python3 eval/run_trials.py --trials 2 --output results/smoke.json
python3 eval/score_results.py --results results/smoke.json
```

## Non-Obvious Dependency and Environment Assumptions
- Docker Compose v2 is required (`docker compose`, not legacy `docker-compose`).
- `external/DataAgentBench` must exist locally because eval scripts read benchmark query folders directly.
- If `external/DataAgentBench` is missing, clone it:
```bash
git clone https://github.com/ucbepic/DataAgentBench.git external/DataAgentBench
```

## DAB-Compatible Function Interface
`agent/data_agent/dab_interface.py` provides:

```python
run_agent(question: str, available_databases: list[dict], schema_info: dict) -> dict
```

## Repository Deliverables Map
- Agent code: `agent/`
- Knowledge base: `kb/`
- Evaluation harness: `eval/`
- Adversarial probes: `probes/probes.md`
- Planning/governance docs: `planning/`
- Signal/communication artifacts: `signal/`
- Benchmark outputs + score log: `results/`
- Shared utility modules: `utils/`
