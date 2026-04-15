# Business Logic Model — U1 Foundation

## Overview
U1 provides the zero-dependency foundation: shared types, environment-driven configuration, event ledger, and text/trace/DB utilities. No orchestration or business workflow logic — purely data structures, configuration, and low-level services.

---

## Module: config.py — Environment Configuration

### Responsibilities
- Read all environment variables with sensible defaults
- Expose typed constants for all modules to import
- Provide offline stub data when `AGENT_OFFLINE_MODE=1`
- Never contain secrets — all sensitive values from `.env` only

### Configuration Groups

**Agent Runtime**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `AGENT_OFFLINE_MODE` | `AGENT_OFFLINE_MODE` | `bool` | `True` (safe default) |
| `AGENT_MAX_TOKENS` | `AGENT_MAX_TOKENS` | `int` | `700` |
| `AGENT_TEMPERATURE` | `AGENT_TEMPERATURE` | `float` | `0.1` |
| `AGENT_TIMEOUT_SECONDS` | `AGENT_TIMEOUT_SECONDS` | `int` | `45` |
| `AGENT_SELF_CORRECTION_RETRIES` | `AGENT_SELF_CORRECTION_RETRIES` | `int` | `3` |
| `AGENT_MAX_EXECUTION_STEPS` | `AGENT_MAX_EXECUTION_STEPS` | `int` | `6` |
| `AGENT_SESSION_ID` | `AGENT_SESSION_ID` | `str` | `""` (auto-generated UUID if empty) |
| `AGENT_USE_MCP` | `AGENT_USE_MCP` | `bool` | `True` |
| `AGENT_USE_SANDBOX` | `AGENT_USE_SANDBOX` | `bool` | `False` |

**MCP / Tool Layer**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `MCP_TOOLBOX_URL` | `MCP_TOOLBOX_URL` | `str` | `"http://localhost:5000"` |
| `MCP_TIMEOUT_SECONDS` | `MCP_TIMEOUT_SECONDS` | `int` | `8` |
| `TOOLS_YAML_PATH` | `TOOLS_YAML_PATH` | `str` | `"./tools.yaml"` |
| `DUCKDB_BRIDGE_URL` | `DUCKDB_BRIDGE_URL` | `str` | `""` (no default pointing to live server per SEC-09) |
| `DUCKDB_BRIDGE_TIMEOUT_SECONDS` | `DUCKDB_BRIDGE_TIMEOUT_SECONDS` | `int` | `8` |
| `DUCKDB_PATH` | `DUCKDB_PATH` | `str` | `"./data/duckdb/main.duckdb"` |

**OpenRouter LLM**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | `str` | `""` |
| `OPENROUTER_MODEL` | `OPENROUTER_MODEL` | `str` | `"google/gemini-2.0-flash-001"` |
| `OPENROUTER_BASE_URL` | `OPENROUTER_BASE_URL` | `str` | `"https://openrouter.ai/api/v1"` |
| `OPENROUTER_APP_NAME` | `OPENROUTER_APP_NAME` | `str` | `"oracle-forge-agent"` |

**Memory**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `AGENT_MEMORY_ROOT` | `AGENT_MEMORY_ROOT` | `str` | `".oracle_forge_memory"` |
| `AGENT_MEMORY_SESSION_ITEMS` | `AGENT_MEMORY_SESSION_ITEMS` | `int` | `12` |
| `AGENT_MEMORY_TOPIC_CHARS` | `AGENT_MEMORY_TOPIC_CHARS` | `int` | `2500` |
| `AGENT_RUNTIME_EVENTS_PATH` | `AGENT_RUNTIME_EVENTS_PATH` | `str` | `".oracle_forge_memory/events.jsonl"` |

**Paths**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `AGENT_CONTEXT_PATH` | `AGENT_CONTEXT_PATH` | `str` | `"agent/AGENT.md"` |
| `AGENT_CORRECTIONS_LOG_PATH` | `AGENT_CORRECTIONS_LOG_PATH` | `str` | `"kb/corrections/corrections_log.md"` |
| `KB_ROOT` | (derived) | `str` | `"kb"` |

**Sandbox**:
| Constant | Env Var | Type | Default |
|---|---|---|---|
| `SANDBOX_URL` | `SANDBOX_URL` | `str` | `"http://localhost:8080"` |
| `SANDBOX_TIMEOUT_SECONDS` | `SANDBOX_TIMEOUT_SECONDS` | `int` | `12` |
| `SANDBOX_MAX_PAYLOAD_CHARS` | `SANDBOX_MAX_PAYLOAD_CHARS` | `int` | `50000` |
| `SANDBOX_PY_TIMEOUT_SECONDS` | `SANDBOX_PY_TIMEOUT_SECONDS` | `int` | `3` |

### Offline Stubs (NFR-01)

When `AGENT_OFFLINE_MODE=1`, `config.py` exports stub data consumed by downstream modules:

**`OFFLINE_LLM_RESPONSE`** — deterministic stub LLM reply:
```python
{
    "choices": [{"message": {"content": "OFFLINE_STUB: This is a deterministic stub response for offline mode testing."}}],
    "model": "offline-stub",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0}
}
```

**`OFFLINE_TOOL_LIST`** — merged 4-tool flat list (matches `tools.yaml` schema):
```python
[
    {"name": "query_postgresql", "kind": "postgres-sql", "source": "postgres_db", "description": "Execute read-only SQL against PostgreSQL"},
    {"name": "query_mongodb", "kind": "mongodb-aggregate", "source": "mongo_db", "description": "Execute aggregation pipeline against MongoDB"},
    {"name": "query_sqlite", "kind": "sqlite-sql", "source": "sqlite_db", "description": "Execute read-only SQL against SQLite"},
    {"name": "query_duckdb", "kind": "duckdb_bridge_sql", "source": "duckdb_bridge", "description": "Execute read-only SQL against DuckDB via custom MCP bridge"}
]
```

**`OFFLINE_INVOKE_RESULTS`** — keyed by db_type:
```python
{
    "postgres": {"success": True, "result": [{"id": 1, "value": "stub_pg"}], "error": ""},
    "mongodb": {"success": True, "result": [{"_id": "1", "field": "stub_mongo"}], "error": ""},
    "sqlite": {"success": True, "result": [{"id": 1, "data": "stub_sqlite"}], "error": ""},
    "duckdb": {"success": True, "result": [{"col1": 42, "col2": "stub_duckdb"}], "error": ""}
}
```

### Logging Configuration (SEC-03)
- Configure Python `logging` module at import time
- Default level: `INFO` (overridable via `LOG_LEVEL` env var)
- Format: `%(asctime)s [%(levelname)s] %(name)s (%(session_id)s): %(message)s`
- No secrets (API keys, DB connection strings, file paths) in log output at INFO+

---

## Module: events.py — Append-Only Event Ledger (FR-06)

### Responsibilities
- `emit_event(event: TraceEvent) -> None` — append a single JSONL line
- Create parent directory and file lazily on first write
- Validate event structure before writing (SEC-13)
- Thread-safe via file-level append mode

### Algorithm: emit_event
```
1. Validate event: assert event_type and session_id and timestamp are non-empty
2. Serialize event to dict via event.to_dict()
3. JSON-encode dict to single line (no pretty-print)
4. Open file in append mode ("a"); create parent dirs if missing
5. Write line + newline
6. Close file handle (use with-statement for resource cleanup per SEC-15)
```

### Algorithm: read_events (utility)
```
1. If file doesn't exist, return empty list
2. Read file line-by-line
3. For each line: json.loads() with try/except (SEC-13)
4. Skip malformed lines (log warning, don't crash)
5. Return list of TraceEvent via from_dict()
```

---

## Module: text_utils.py — Text Processing Utilities (FR-09 support)

### Responsibilities
- Keyword extraction from natural language queries
- Document overlap scoring for KB retrieval
- Filename stem overlap for file-level matching
- Freshness bonus based on file modification time

### Algorithm: extract_keywords(text: str) -> list[str]
```
1. Lowercase the text
2. Tokenize by splitting on whitespace and punctuation
3. Remove stop words (English stop word list, ~150 words)
4. Remove tokens shorter than 2 characters
5. Deduplicate while preserving order
6. Return keyword list
```

**Invariant**: Returns empty list for empty input; returns subset of input tokens (PBT-03).

### Algorithm: score_overlap(keywords: list[str], document: str) -> float
```
1. If keywords is empty, return 0.0
2. Lowercase document text
3. Count how many keywords appear in document (exact substring match)
4. Score = matched_count / len(keywords)
5. Return score in [0.0, 1.0]
```

**Invariant**: Score always in [0.0, 1.0]; score([], doc) == 0.0 (PBT-03).

### Algorithm: filename_stem_overlap(keywords: list[str], filename: str) -> float
```
1. Extract stem from filename (strip extension, split on _ and -)
2. Score = count of keywords matching any stem token / len(keywords)
3. Return score in [0.0, 1.0]
```

### Algorithm: freshness_bonus(file_path: str) -> float
```
1. Get file modification time
2. Calculate age_days = (now - mtime).days
3. If age_days <= 1: return 0.3 (very fresh)
4. If age_days <= 7: return 0.2
5. If age_days <= 30: return 0.1
6. Else: return 0.0
7. On file-not-found: return 0.0 (safe fallback per SEC-15)
```

---

## Module: trace_utils.py — Trace Event Builders

### Responsibilities
- Factory functions for constructing `TraceEvent` instances with sensible defaults
- Human-readable trace summary formatting

### Functions

**`build_trace_event(event_type, session_id, **kwargs) -> TraceEvent`**:
- Sets `timestamp` to current ISO 8601 if not provided
- Fills all optional fields with defaults from TraceEvent
- Returns fully-populated TraceEvent

**`format_trace_summary(events: list[TraceEvent]) -> str`**:
- Groups events by session_id
- Formats each event as: `[timestamp] event_type: tool_name (outcome) retry=N`
- Returns multi-line string

---

## Module: db_utils.py — Database Utility Stubs

### Responsibilities
- `db_type_from_kind(kind: str) -> str` — map tool kind to DB type
- `validate_db_url(url: str, db_type: str) -> bool` — basic URL format validation
- `sanitize_sql_for_log(sql: str) -> str` — truncate/redact SQL for safe logging (SEC-03)

### Mapping: kind -> db_type
```python
{
    "postgres-sql": "postgres",
    "mongodb-aggregate": "mongodb",
    "sqlite-sql": "sqlite",
    "duckdb_bridge_sql": "duckdb"
}
```

### Algorithm: sanitize_sql_for_log(sql: str) -> str
```
1. Truncate to first 100 characters
2. Replace string literals ('...') with '<STR>'
3. Replace numeric sequences in WHERE clauses with '<NUM>'
4. Return sanitized string
```
