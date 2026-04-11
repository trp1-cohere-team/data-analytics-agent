# Infrastructure Design
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes  
**Deployment Model**: In-process library — no standalone infrastructure

---

## Infrastructure Summary

U5 has no standalone infrastructure. All modules are Python packages imported at runtime by U1 (ContextManager, Orchestrator) and U2 (MultiDBEngine). The only external runtime dependency is the MCP Toolbox process, which is shared project infrastructure documented in `shared-infrastructure.md`.

| Concern | Resolution |
|---|---|
| Process | None — U5 code runs inside the U1 FastAPI process |
| Storage | None — `probes/probes.md` is a version-controlled flat file |
| Network | One outbound HTTP connection per `introspect_all()` call → MCP Toolbox localhost:5000 |
| Secrets | None — no API keys, no credentials in U5 |
| Monitoring | Inherits parent process logging (U1 configures the root logger) |

---

## Runtime Dependency: MCP Toolbox

`SchemaIntrospector` is the only U5 module that makes network calls. It calls the MCP Toolbox process over HTTP.

| Property | Value |
|---|---|
| Protocol | HTTP (no TLS — localhost only) |
| Base URL | `config.MCP_TOOLBOX_URL` (default: `http://localhost:5000`) |
| Called at | Server startup only (`ContextManager.startup_load()`) |
| Frequency | Once per server process lifetime (Layer 1 permanent cache) |
| Timeout | 9s outer + per-DB sub-limits (see NFR Design) |
| Error handling | Returns empty `DBSchema` with `error` field — never blocks startup |

The MCP Toolbox process must be running before the agent server starts. Start order: `mcp-toolbox serve --config tools.yaml` → then `uvicorn agent.api.app:app`.

---

## File System Footprint

U5 touches these paths at runtime:

| Path | Access | Description |
|---|---|---|
| `probes/probes.md` | Read (ProbeRunner) | Probe definitions loaded at probe execution time |
| `probes/probe_runner.py` | Execute | ProbeRunner script — run manually by developer |

No writes to file system at runtime. `probes.md` is only written by the developer when documenting probe results.

---

## Logging

U5 modules use the standard Python `logging` module with the module-level logger pattern:

```python
import logging
logger = logging.getLogger(__name__)
```

Log levels:
- `WARNING` — MCP Toolbox call failed (SchemaIntrospector graceful degradation)
- `DEBUG` — IDF computation enabled/disabled, per-pass keyword match counts
- `INFO` — `introspect_all()` completion summary (N DBs introspected, M failed)

Root logger configuration is owned by U1 (`agent/api/app.py`). U5 modules do not configure handlers or formatters.

---

## Test Infrastructure

U5 unit tests run without any external services. SchemaIntrospector tests use a mock HTTP client injected via dependency injection. ProbeRunner tests use a mock HTTP client in place of the live agent.

| Test Type | Requires | Run Command |
|---|---|---|
| Unit tests | Nothing (mock HTTP) | `pytest tests/unit/test_*.py -v` |
| PBT tests | Nothing (pure functions) | `pytest tests/unit/test_join_key_utils.py -v` |
| Integration tests | MCP Toolbox running | `pytest tests/integration/ -v` |
| Probe execution | Agent running + MCP Toolbox | `python probes/probe_runner.py` |
