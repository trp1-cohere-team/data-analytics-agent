# Build Instructions — The Oracle Forge

**Project**: Data Analytics Agent  
**Build Tool**: pip + Python 3.11+  
**Date**: 2026-04-11

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Required for `asyncio.TaskGroup`, `match` syntax |
| pip | Latest | `pip install --upgrade pip` |
| MCP Toolbox binary | Latest | Download from toolbox releases; must be on `$PATH` |
| PostgreSQL | 14+ | For integration tests |
| SQLite | 3.35+ | Bundled with Python stdlib |
| MongoDB | 5+ | For integration tests (optional) |
| DuckDB | 0.9+ | Installed via pip |

### Required Environment Variables

```bash
# LLM API
OPENROUTER_API_KEY=<your-key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1      # default
OPENROUTER_MODEL=openai/gpt-4o                        # default

# MCP Toolbox
MCP_TOOLBOX_URL=http://localhost:5000                 # default

# Agent server
AGENT_PORT=8000                                       # default
```

Create a `.env` file in the workspace root or export these before running any command.

---

## Build Steps

### 1. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected output**: All packages install without errors. `aiohttp`, `openai`, `fastapi`, `slowapi`, `hypothesis`, `pydantic`, `pydantic-settings` must be present.

### 3. Verify Package Structure

```bash
python -c "import agent; import eval; import utils; import probes; print('OK')"
```

**Expected output**: `OK` — no import errors.

### 4. Configure MCP Toolbox

```bash
# Start the MCP Toolbox (required for integration tests and live benchmarks)
mcp-toolbox --config tools.yaml &

# Verify it responds
curl http://localhost:5000/v1/tools
```

### 5. Initialise Knowledge Base Structure

```bash
python -c "
from agent.kb.knowledge_base import KnowledgeBase
from pathlib import Path
import asyncio
kb = KnowledgeBase(kb_dir=Path('kb'))
asyncio.run(kb._ensure_kb_structure())
print('KB structure OK')
"
```

---

## Build Artifacts

| Artifact | Location | Created By |
|---|---|---|
| Agent package | `agent/` | Code generation (U1–U3) |
| Evaluation harness | `eval/` | Code generation (U4) |
| Utilities | `utils/` | Code generation (U5) |
| Probe definitions | `probes/` | Code generation (U5) |
| Knowledge base dirs | `kb/` | KB initialisation step above |
| Memory dirs | `agent/memory/` | Created at first agent startup |
| Results directory | `results/` | Created by evaluation harness at first run |

---

## Troubleshooting

### Import errors on `agent.*`
**Cause**: Virtual environment not activated, or `pip install` incomplete.  
**Fix**: Re-run `pip install -r requirements.txt` inside the active venv.

### `MCP_TOOLBOX_URL connection refused`
**Cause**: MCP Toolbox not running.  
**Fix**: Start with `mcp-toolbox --config tools.yaml` before running the agent or integration tests.

### `OPENROUTER_API_KEY not set`
**Cause**: Environment variable missing.  
**Fix**: Export from `.env` or shell: `export OPENROUTER_API_KEY=<key>`.

### `hypothesis.errors.HypothesisDeprecationWarning`
**Cause**: Hypothesis version mismatch.  
**Fix**: `pip install "hypothesis>=6.100.0"`.
