# Unit of Work — Story Map

*(User Stories stage was skipped — Q7=B. This map links requirements directly to units.)*

## Requirement-to-Unit Mapping

| Requirement | Unit |
|---|---|
| FR-01: Agent Facade (`run_agent`) | U4 |
| FR-02: 6-Layer Context Pipeline | U2 (`context_layering.py`) |
| FR-03: Unified `MCPClient` — 4-DB tool registry from `tools.yaml`; dispatch by `kind` field | U2 (`mcp_toolbox_client.py`) + U3 (`tooling.py`) |
| FR-03 (config): `tools.yaml` — single MCP config declaring all 4 DB tool kinds | U5 (`tools.yaml`) |
| FR-03b: DuckDB Bridge contract (internal wire protocol; `kind: duckdb_bridge_sql`) | U2 (`duckdb_bridge_client.py` — private impl) |
| FR-04: Self-Correction Loop | U3 (`conductor.py`) + U4 (`execution_planner.py`) |
| FR-05: Persistent Memory | U3 (`memory.py`) |
| FR-06: Append-Only Event Ledger | U1 (`events.py`) |
| FR-07: DAB Evaluation Harness | U5 (`eval/`) |
| FR-08: AGENT.md Loaded at Session Start | U4 (`oracle_forge_agent.py`) |
| FR-09: Knowledge Base (seed + retrieval) | U2 (`knowledge_base.py`) + U5 (`kb/`) |
| FR-10: Sandbox Execution Path | U4 (`sandbox_server.py`, `sandbox_client.py`) |
| FR-11: Adversarial Probes | U5 (`probes/probes.md`) |
| FR-12: Shared Types Module | U1 (`types.py`) |
| FR-13: LLM Backend Configurable | U1 (`config.py`) + U4 (`execution_planner.py`, `result_synthesizer.py`) |
| NFR-01: Offline Mode | U1 (`config.py` stubs) + U2 (stub returns) + U4 (stub LLM) |
| NFR-02: Timeout Guards | U2 (`mcp_toolbox_client.py`) + U3 (`conductor.py`) |
| NFR-03: Retry Cap | U3 (`conductor.py`) |
| NFR-04: No Secrets in Code | U1 (`config.py`) — all from env |
| NFR-05: Test Suite | U5 (`tests/`) |
| SEC-03: Structured Logging | All units — `logging` framework throughout |
| SEC-05: Input Validation | U3 (`tooling.py` `ToolPolicy`) + U4 facade |
| SEC-10: Supply Chain / Pinned Deps | U5 (`requirements.txt`) |
| SEC-15: Exception Handling | U3 (`conductor.py`) global handler |
| PBT-02: Round-Trip Tests | U5 (`tests/test_properties.py`) |
| PBT-03: Invariant Tests | U5 (`tests/test_properties.py`) |

## Acceptance Test Coverage

| Test | Unit Under Test | Test File |
|---|---|---|
| `test_conductor.py` | U3 | `tests/test_conductor.py` |
| `test_context_layering.py` | U2 | `tests/test_context_layering.py` |
| `test_failure_diagnostics.py` | U2 | `tests/test_failure_diagnostics.py` |
| `test_memory.py` | U3 | `tests/test_memory.py` |
| `test_properties.py` (Hypothesis) | U1+U2 | `tests/test_properties.py` |
| DAB smoke test | U4+U5 | `eval/run_trials.py --trials 2` |
