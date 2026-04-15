# Build Instructions — OracleForge Data Agent

## Prerequisites
- **Python**: 3.11+
- **Build Tool**: pip (no compilation step — pure Python)
- **System Requirements**: Linux/macOS, 512MB RAM minimum

## Build Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

Pinned packages installed:
- `requests==2.32.3` — HTTP client (MCP Toolbox, DuckDB bridge, OpenRouter)
- `flask==3.1.0` — Sandbox server
- `pyyaml==6.0.2` — tools.yaml parsing
- `python-dotenv==1.1.0` — .env loading
- `hypothesis==6.131.7` — Property-based testing (PBT-09)
- `werkzeug==3.1.3` — Flask dependency

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env — minimum for offline mode:
# AGENT_OFFLINE_MODE=1
```

### 3. Verify Imports (All Units)
```bash
AGENT_OFFLINE_MODE=1 python3 -c "
from agent.data_agent.oracle_forge_agent import run_agent
from agent.data_agent.execution_planner import build_plan
from agent.data_agent.result_synthesizer import synthesize_answer
from agent.data_agent.sandbox_client import SandboxClient
from eval.score_results import compute_pass_at_1
print('All imports OK')
"
```

### 4. Verify Build Success
- **Expected Output**: `All imports OK`
- **No compilation step** — Python imports serve as build verification
- **Build Artifacts**: Source files in workspace root (no generated artifacts)

## Troubleshooting

### Missing module error
- **Cause**: Package not installed or wrong Python version
- **Solution**: `pip install -r requirements.txt` and verify `python3 --version` >= 3.11

### Import error on config.py
- **Cause**: env vars with invalid types (e.g., non-int for AGENT_MAX_TOKENS)
- **Solution**: Remove invalid values from .env; defaults in config.py are safe

### YAML parse error on tools.yaml
- **Cause**: Unquoted `${}` expressions in tools.yaml if strict YAML mode
- **Solution**: tools.yaml uses shell-style `${VAR}` placeholders — MCPClient handles them; raw YAML parsers may warn
