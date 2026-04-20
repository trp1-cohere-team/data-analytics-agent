# Agent Directory Guide

This directory contains the core runtime and agent logic.

## Contents
- `data_agent/`: Main OracleForge agent implementation (planning, tool execution, synthesis, context layering).
- `runtime/`: Session/runtime infrastructure (memory, conductor, events, tooling policy).
- `AGENT.md`: Agent identity and behavior constraints loaded as institutional knowledge.
- `tools.yaml`: Tool configuration used by the runtime.
- `requirements.txt`: Agent-specific Python dependencies.

## Entry Points
- CLI query path: `python3 -m agent.data_agent.cli "<question>" --db-hints '["sqlite","duckdb"]'`
- DAB-compatible interface: `agent/data_agent/dab_interface.py` (`run_agent(...)`).
