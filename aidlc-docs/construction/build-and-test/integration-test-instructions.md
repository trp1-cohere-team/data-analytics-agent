# Integration Test Instructions — OracleForge Data Agent

## Purpose
Test the full agent pipeline end-to-end using offline stubs and then with live services.

## Offline Integration Tests (No External Services Required)

### Scenario 1: Full Pipeline (U1→U2→U3→U4)
```bash
AGENT_OFFLINE_MODE=1 python3 -c "
from agent.data_agent.oracle_forge_agent import run_agent
result = run_agent('How many books are there?', ['postgres'])
assert result.answer, 'No answer returned'
assert 0.0 <= result.confidence <= 1.0, 'Confidence out of range'
assert result.trace_id, 'No trace_id'
print('Full pipeline integration: PASS')
print('Answer:', result.answer[:100])
"
```

### Scenario 2: eval/run_trials.py + score_results.py Pipeline
```bash
# Run trials
AGENT_OFFLINE_MODE=1 python3 eval/run_trials.py \
  --trials 2 \
  --output results/integration_test.json

# Score results
python3 eval/score_results.py \
  --results results/integration_test.json \
  --output-dir results/

# Verify output files
ls results/dab_detailed.json results/dab_submission.json
```

### Scenario 3: Knowledge Base Retrieval
```bash
AGENT_OFFLINE_MODE=1 python3 -c "
from agent.data_agent.knowledge_base import load_layered_kb_context
results = load_layered_kb_context('average rating books decade')
print(f'KB retrieved {len(results)} documents')
for content, score in results[:3]:
    print(f'  score={score:.3f} content={content[:60]!r}')
"
```

### Scenario 4: Memory Round-Trip
```bash
AGENT_OFFLINE_MODE=1 python3 -c "
import os
os.environ['AGENT_MEMORY_ROOT'] = '/tmp/test_integration_memory'
from agent.runtime.memory import MemoryManager
from agent.data_agent.types import MemoryTurn
from datetime import datetime, timezone
m = MemoryManager(session_id='integration-test')
m.save_turn(MemoryTurn(role='user', content='test question', timestamp=datetime.now(timezone.utc).isoformat(), session_id='integration-test'))
ctx = m.get_memory_context()
print('Memory context len:', len(ctx))
print('Integration memory test: PASS')
import shutil
shutil.rmtree('/tmp/test_integration_memory', ignore_errors=True)
"
```

## Live Service Integration Tests (Optional — Requires Running Services)

### Prerequisites
```bash
# Start Google MCP Toolbox
# (See MCP Toolbox documentation)
export MCP_TOOLBOX_URL=http://localhost:5000

# Start DuckDB bridge
export DUCKDB_BRIDGE_URL=http://localhost:5001
export DUCKDB_PATH=./data/duckdb/main.duckdb

# Set OpenRouter key
export OPENROUTER_API_KEY=your_key_here
export AGENT_OFFLINE_MODE=0
```

### Live Pipeline Test
```bash
python3 eval/run_trials.py \
  --trials 1 \
  --datasets bookreview \
  --output results/live_test.json
python3 eval/score_results.py --results results/live_test.json
```

### Sandbox Integration Test
```bash
# Start sandbox server in background
SANDBOX_ALLOWED_ROOTS=/tmp python3 sandbox/sandbox_server.py &
SANDBOX_PID=$!

# Test health check
curl -s http://localhost:8080/health

# Test execution
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"code": "print(2+2)", "timeout": 3}'

kill $SANDBOX_PID
```
