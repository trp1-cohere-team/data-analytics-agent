# Architecture Injection Tests

## Test A1
- Prompt: "How does OracleForge route tools across 4 database types?"
- Expected answer: "Through one `MCPClient` registry loaded from `tools.yaml`; toolbox kinds go to MCP toolbox and `duckdb_bridge_sql` goes to the DuckDB bridge client."

## Test A2
- Prompt: "What is the role of the conductor in this codebase?"
- Expected answer: "Conductor orchestrates context assembly, tool invocation, self-correction, memory writes, and event emission."

## Test A3
- Prompt: "When is sandbox execution used?"
- Expected answer: "When `AGENT_USE_SANDBOX=1` and the runtime uses `execute_python` tool; execution goes through `sandbox/sandbox_server.py`."
