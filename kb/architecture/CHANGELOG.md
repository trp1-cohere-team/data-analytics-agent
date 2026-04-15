# Architecture KB Changelog

## 2026-04-15
- Added references for unified `MCPClient` routing across PostgreSQL, MongoDB, SQLite, and DuckDB bridge.
- Clarified sandbox execution path (`execute_python`) as optional runtime tool activated by `AGENT_USE_SANDBOX=1`.
- Synced architecture notes with current runtime modules under `agent/runtime/` and `agent/data_agent/`.
- Added `claude-openai-context-design.md` to document Claude memory principles and OpenAI-style layered context design.
- Added per-document injection test evidence sections for architecture context injection validation.
