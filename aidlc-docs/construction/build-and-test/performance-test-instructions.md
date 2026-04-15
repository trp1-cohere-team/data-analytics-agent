# Performance Test Instructions — OracleForge Data Agent

## Performance Requirements (NFR-02/03/06)

| Metric | Requirement |
|--------|------------|
| LLM call timeout | ≤ AGENT_TIMEOUT_SECONDS (default 45s) |
| MCP Toolbox call | ≤ MCP_TIMEOUT_SECONDS (default 8s) |
| DuckDB bridge call | ≤ DUCKDB_BRIDGE_TIMEOUT_SECONDS (default 8s) |
| Sandbox execution | ≤ SANDBOX_PY_TIMEOUT_SECONDS (default 3s) |
| Session memory | ≤ AGENT_MEMORY_SESSION_ITEMS (default 12 turns) |
| Topic memory | ≤ AGENT_MEMORY_TOPIC_CHARS (default 2500 chars) |

## Offline Throughput Test

Measures offline pipeline throughput (no external API calls):

```bash
AGENT_OFFLINE_MODE=1 python3 -c "
import time
from agent.data_agent.oracle_forge_agent import run_agent

questions = [
    ('How many books?', ['postgres']),
    ('Top 5 artists', ['mongodb']),
    ('Average rating', ['sqlite']),
    ('Recent stocks', ['duckdb']),
    ('Genre distribution', ['postgres', 'sqlite']),
]

start = time.monotonic()
for q, hints in questions * 4:  # 20 runs
    result = run_agent(q, hints)
    assert result.answer

elapsed = time.monotonic() - start
rps = 20 / elapsed
print(f'20 offline runs in {elapsed:.2f}s ({rps:.1f} req/s)')
"
```

## Memory Footprint Test

```bash
AGENT_OFFLINE_MODE=1 python3 -c "
import os, tracemalloc
tracemalloc.start()
from agent.data_agent.oracle_forge_agent import run_agent
result = run_agent('test question', ['postgres'])
current, peak = tracemalloc.get_traced_memory()
print(f'Peak memory: {peak / 1024 / 1024:.1f} MB')
tracemalloc.stop()
"
```

## Session Memory Cap Verification

```bash
AGENT_OFFLINE_MODE=1 python3 -c "
import os
os.environ['AGENT_MEMORY_ROOT'] = '/tmp/test_perf_memory'
from agent.data_agent.oracle_forge_agent import OracleForgeAgent

agent = OracleForgeAgent(session_id='perf-test-001')
for i in range(20):  # Exceeds cap of 12
    agent.run_agent(f'Question {i}', ['postgres'])

import json, shutil
session_file = '/tmp/test_perf_memory/sessions/perf-test-001.jsonl'
if os.path.exists(session_file):
    lines = open(session_file).readlines()
    print(f'Session file has {len(lines)} turns (cap=12)')
    assert len(lines) <= 12, f'Session cap exceeded: {len(lines)} > 12'
    print('Memory cap test: PASS')
shutil.rmtree('/tmp/test_perf_memory', ignore_errors=True)
"
```

## Notes
- Performance tests are for validation only — no SLA enforcement in offline mode
- Live mode performance depends on OpenRouter latency (target: <5s p95 per query)
- For load testing with live services: use locust or k6 targeting run_agent()
