# Domain Entities — U1 Foundation

## Overview
All shared dataclasses live in `agent/data_agent/types.py`. They are imported by every unit in the system. All use `@dataclass` with type annotations. Zero side effects on import.

---

## Entity: AgentResult (FR-01)
**Purpose**: Single return type from `run_agent()` — the public API facade.

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | Final synthesized answer text |
| `confidence` | `float` | Confidence score in [0.0, 1.0] |
| `trace_id` | `str` | UUID linking to event ledger entries |
| `tool_calls` | `list[dict]` | Ordered list of tool invocations `{tool_name, params, result_summary}` |
| `failure_count` | `int` | Number of failed attempts before final answer (0 = first try success) |

**Invariants**: `confidence` in [0.0, 1.0]; `failure_count` >= 0; `trace_id` is non-empty UUID string.

---

## Entity: TraceEvent (FR-06)
**Purpose**: Structured JSONL event for the append-only event ledger.

| Field | Type | Default | Description |
|---|---|---|---|
| `event_type` | `str` | (required) | Event category: `tool_call`, `tool_result`, `correction`, `agent_context_loaded`, `plan_step`, `session_start`, `session_end` |
| `session_id` | `str` | (required) | Session correlation ID |
| `timestamp` | `str` | (required) | ISO 8601 timestamp |
| `tool_name` | `str` | `""` | Tool invoked (empty if not a tool event) |
| `db_type` | `str` | `""` | Database type: `postgres`, `mongodb`, `sqlite`, `duckdb`, or empty |
| `input_summary` | `str` | `""` | Truncated summary of input (no secrets) |
| `outcome` | `str` | `""` | `success`, `failure`, `timeout`, `corrected` |
| `diagnosis` | `str` | `""` | Failure category if applicable |
| `retry_count` | `int` | `0` | Current retry number (0-based) |
| `backend` | `str` | `""` | `mcp_toolbox` or `duckdb_bridge` (distinguishes providers) |
| `extra` | `dict` | `{}` | Extensible metadata (future-proof) |

**Serialization**: `to_dict() -> dict` and `from_dict(d: dict) -> TraceEvent`. Round-trip property: `TraceEvent.from_dict(e.to_dict()) == e` (PBT-02).

---

## Entity: ContextPacket (FR-02)
**Purpose**: 6-layer context composition for LLM prompts. Precedence: Layer 6 (highest) to Layer 1 (lowest).

| Field | Type | Layer | Description |
|---|---|---|---|
| `table_usage` | `str` | 1 | DB inventory, schema summary, join-key hints |
| `human_annotations` | `str` | 2 | Query-aware retrieval from `kb/domain/` |
| `institutional_knowledge` | `str` | 3 | `kb/architecture/` + `kb/evaluation/` + `AGENT.md` |
| `runtime_context` | `dict` | 4 | `{session_id, discovered_tools, selected_dbs, route_proposals, mode_flags}` |
| `interaction_memory` | `str` | 5 | Runtime memory + `kb/corrections/` |
| `user_question` | `str` | 6 | Latest user question (highest precedence) |

**Backward-compat aliases** (property accessors):
- `schema_and_metadata` -> `table_usage`
- `institutional_and_domain` -> `human_annotations` + `"\n\n"` + `institutional_knowledge`

**Serialization**: `to_dict() -> dict` and `from_dict(d: dict) -> ContextPacket`. Round-trip property (PBT-02).

**Invariant**: Layer 6 always overrides Layer 1 when assembling the final prompt (PBT-03).

---

## Entity: ExecutionStep (FR-04)
**Purpose**: Single step in a multi-step execution plan.

| Field | Type | Default | Description |
|---|---|---|---|
| `step_number` | `int` | (required) | 1-based step index |
| `action` | `str` | (required) | Description of what to do |
| `tool_name` | `str` | `""` | MCP tool to invoke (empty for non-tool steps) |
| `parameters` | `dict` | `{}` | Tool invocation parameters |
| `expected_outcome` | `str` | `""` | What success looks like |
| `status` | `str` | `"pending"` | One of: `pending`, `success`, `failed`, `corrected` |

**Invariant**: `status` always in `{"pending", "success", "failed", "corrected"}`.

---

## Entity: CorrectionEntry (FR-04)
**Purpose**: Structured entry for `kb/corrections/corrections_log.md`.

| Field | Type | Description |
|---|---|---|
| `timestamp` | `str` | ISO 8601 |
| `session_id` | `str` | Session correlation ID |
| `original_error` | `str` | Sanitized error message (SQL stripped to summary per SEC-09) |
| `diagnosis_category` | `str` | One of: `query`, `join-key`, `db-type`, `data-quality` |
| `correction_applied` | `str` | Description of the correction |
| `retry_number` | `int` | Which retry attempt (1-based) |
| `outcome` | `str` | `success` or `failed` |

---

## Entity: LayerContent (FR-02 support)
**Purpose**: Individual layer data before composition into ContextPacket.

| Field | Type | Description |
|---|---|---|
| `layer_number` | `int` | 1-6 |
| `layer_name` | `str` | Human-readable name (e.g., `"table_usage"`, `"user_question"`) |
| `content` | `str` | The layer's text content |
| `precedence` | `int` | Same as `layer_number` (higher = higher priority) |

---

## Entity: FailureDiagnosis (FR-04 support)
**Purpose**: Output of `failure_diagnostics.classify()`.

| Field | Type | Description |
|---|---|---|
| `category` | `str` | One of: `query`, `join-key`, `db-type`, `data-quality` |
| `explanation` | `str` | Human-readable explanation of the failure |
| `suggested_fix` | `str` | Suggested correction action (may be empty) |
| `original_error` | `str` | Raw error string from the backend |

**Invariant**: `category` always in `{"query", "join-key", "db-type", "data-quality"}` (PBT-03).

---

## Entity: ToolDescriptor (FR-03 support)
**Purpose**: Describes a single MCP tool from the unified registry.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Tool name (e.g., `query_postgresql`, `query_duckdb`) |
| `kind` | `str` | Tool kind from `tools.yaml` (e.g., `postgres-sql`, `duckdb_bridge_sql`) |
| `source` | `str` | Source name from `tools.yaml` (e.g., `postgres_db`, `duckdb_bridge`) |
| `description` | `str` | Human-readable tool description |
| `parameters` | `dict` | Tool parameter schema (optional) |
| `schema_summary` | `str` | DB schema summary (optional, populated after discovery) |

---

## Entity: InvokeResult (FR-03 support)
**Purpose**: Unified result from any tool invocation (MCP Toolbox or DuckDB bridge).

| Field | Type | Default | Description |
|---|---|---|---|
| `success` | `bool` | (required) | Whether the invocation succeeded |
| `result` | `object` | `None` | Query result rows/data (None on failure) |
| `error` | `str` | `""` | Error message if failed |
| `error_type` | `str` | `""` | Error category: `query`, `policy`, `config`, `timeout`, or empty |
| `tool_name` | `str` | (required) | Which tool was invoked |
| `db_type` | `str` | `""` | `postgres`, `mongodb`, `sqlite`, `duckdb` |

---

## Entity: MemoryTurn (FR-05 support)
**Purpose**: Single turn in the session transcript (`.jsonl`).

| Field | Type | Description |
|---|---|---|
| `role` | `str` | `"user"` or `"assistant"` |
| `content` | `str` | Turn content text |
| `timestamp` | `str` | ISO 8601 |
| `session_id` | `str` | Session correlation ID |

---

## Entity Relationship Summary

```
AgentResult <-- produced by --> OracleForgeAgent (U4)
     |
     +-- contains --> tool_calls (list of dicts)
     +-- links via trace_id --> TraceEvent (event ledger)

ContextPacket <-- composed from --> LayerContent (6 layers)
     |
     +-- Layer 5 uses --> MemoryTurn (session transcript)
     +-- Layer 3 uses --> KB documents

ExecutionStep <-- sequenced in --> execution plan
     |
     +-- on failure --> FailureDiagnosis
     +-- on correction --> CorrectionEntry

ToolDescriptor <-- loaded from --> tools.yaml
     |
     +-- invoked via --> MCPClient.invoke_tool()
     +-- returns --> InvokeResult
```
