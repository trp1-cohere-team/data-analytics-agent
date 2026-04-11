# Deployment Architecture
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## Deployment Model: In-Process Library

U5 is not deployed independently. It is installed as part of the Python package and imported by other units at runtime.

```
Developer Machine (local)
│
├── Process 1: MCP Toolbox
│     mcp-toolbox serve --config tools.yaml
│     Listens: localhost:5000
│     Manages: PostgreSQL, SQLite, MongoDB, DuckDB connections
│
└── Process 2: FastAPI Agent Server
      uvicorn agent.api.app:app --port 8000
      │
      ├── [U1] agent/api/, orchestrator/, context/, correction/
      ├── [U2] agent/execution/
      ├── [U3] agent/kb/, agent/memory/
      └── [U5] utils/  ← imported by U1 and U2, runs in this process
            schema_introspector.py  → HTTP → MCP Toolbox (localhost:5000)
            multi_pass_retriever.py → in-memory only
            join_key_utils.py       → in-memory only
            benchmark_wrapper.py   → HTTP → AgentAPI (localhost:8000)
```

---

## Startup Sequence

```
1. Start MCP Toolbox:
     mcp-toolbox serve --config tools.yaml
     Wait for: GET http://localhost:5000/health → 200 OK

2. Start Agent Server:
     uvicorn agent.api.app:app --host 0.0.0.0 --port 8000
     On startup event:
       a. ContextManager.startup_load()
            → SchemaIntrospector.introspect_all("http://localhost:5000")
            → asyncio.timeout(9s) + per-DB limits
            → SchemaContext cached in memory (Layer 1)
       b. ContextManager._refresh_layer2_if_stale() background task started
     Ready: server accepts requests

3. (Optional) Run probes:
     python probes/probe_runner.py --probe-id ROUTING-001
     Requires: agent server running on port 8000
```

---

## Package Structure (U5 contribution to workspace root)

```
data-analytics-agent/          ← workspace root
  utils/
    __init__.py
    schema_introspector.py
    multi_pass_retriever.py
    join_key_utils.py
    benchmark_wrapper.py
  probes/
    __init__.py
    probes.md                  ← adversarial probe definitions (15+ entries)
    probe_runner.py
  tests/
    unit/
      strategies.py            ← Hypothesis @st.composite strategy factory
      test_join_key_utils.py   ← PBT + unit tests (5 invariant properties)
      test_multi_pass_retriever.py
      test_schema_introspector.py
      test_probe_runner.py
    integration/
      test_schema_introspection_live.py  ← requires MCP Toolbox running
```

---

## No Cloud Infrastructure

This project runs entirely on a local developer machine (confirmed in requirements: "No shared server, running locally"). No cloud resources, containers, or CI/CD pipelines are required for U5. The only external process is MCP Toolbox, which runs as a local binary.
