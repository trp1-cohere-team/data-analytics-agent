# Business Logic Model — U2 Data Layer

## Overview
U2 provides the data transformation and retrieval layer: knowledge base access, 6-layer context composition, failure classification, and the unified multi-database tool interface. No orchestration logic — pure data operations.

---

## Module: knowledge_base.py — KB Retrieval (FR-09)

### Responsibilities
- Load `.md` documents from `kb/` subdirectories (architecture, domain, evaluation, corrections)
- Keyword-based retrieval with weighted ranking
- Return ranked documents relevant to a query

### Public API

**`load_layered_kb_context(query: str, categories: list[str] | None = None) -> list[tuple[str, float]]`**

Returns list of `(document_content, relevance_score)` tuples sorted by descending score.

### Algorithm: load_layered_kb_context
```
1. If categories is None, use all: ["architecture", "domain", "evaluation", "corrections"]
2. For each category, scan kb/{category}/*.md
3. For each document:
   a. Read file content
   b. Extract keywords from query using text_utils.extract_keywords()
   c. Compute content_score = text_utils.score_overlap(keywords, document)
   d. Compute filename_score = text_utils.filename_stem_overlap(keywords, filename)
   e. Compute freshness = text_utils.freshness_bonus(filepath)
   f. final_score = 0.6 * content_score + 0.25 * filename_score + 0.15 * freshness
4. Sort by final_score descending
5. Return top results (all with score > 0.0)
```

### Error Handling
- Missing `kb/` directory: return empty list, log warning (SEC-15)
- Unreadable file: skip with warning, continue scanning (SEC-15)
- Empty query: return empty list

---

## Module: context_layering.py — 6-Layer Context Pipeline (FR-02)

### Responsibilities
- Compose 6 layers into a `ContextPacket` with correct precedence
- Support partial layer population (not all layers required)
- Enforce precedence order: Layer 6 > Layer 5 > ... > Layer 1
- Provide backward-compat aliases

### Public API

**`build_context_packet(layers: dict[str, str | dict] | None = None, **kwargs) -> ContextPacket`**

Accepts either a dict with layer names as keys, or keyword arguments matching ContextPacket fields.

**`assemble_prompt(packet: ContextPacket) -> str`**

Assembles the context layers into a single prompt string, ordered by precedence (highest first).

### Algorithm: build_context_packet
```
1. Initialize empty ContextPacket
2. Apply layers dict if provided (mapping layer names to field values)
3. Apply kwargs overrides (highest priority)
4. Validate all string fields are str type
5. Return ContextPacket
```

### Algorithm: assemble_prompt
```
1. Define layer order (Layer 6 first — highest precedence):
   [user_question, interaction_memory, runtime_context, institutional_knowledge, human_annotations, table_usage]
2. For each layer with non-empty content:
   a. Add section header: "## {layer_name}"
   b. Add content
3. For runtime_context (dict): serialize to formatted key-value pairs
4. Return assembled string
```

### Precedence Invariant (PBT-03)
Layer 6 (user_question) content always appears before Layer 1 (table_usage) in assembled prompt.

---

## Module: failure_diagnostics.py — Failure Classifier (FR-04)

### Responsibilities
- Classify tool invocation failures into exactly one of 4 categories
- Map DuckDB bridge `error_type` to failure categories
- Provide explanation and suggested fix for each classification

### Public API

**`classify(error: str, context: dict | None = None) -> FailureDiagnosis`**

### Classification Rules

| Error Pattern | Category | Suggested Fix |
|---|---|---|
| SQL syntax error, parse error, unknown column/table | `query` | Rewrite query with correct syntax/names |
| Wrong join key, column mismatch in JOIN, FK violation | `join-key` | Check schema for correct join columns |
| Wrong DB selected, unsupported operation for DB type, `error_type=="policy"`, `error_type=="config"` | `db-type` | Switch to correct database tool |
| Empty result, NULL values, data format mismatch, encoding | `data-quality` | Verify data exists and format assumptions |
| Timeout, connection refused | `db-type` | Check service availability |

### Algorithm: classify
```
1. Extract error_type from context if available (DuckDB bridge provides this)
2. If error_type == "policy": return FailureDiagnosis(category="db-type", ...)
3. If error_type == "config": return FailureDiagnosis(category="db-type", ...)
4. If error_type == "query": return FailureDiagnosis(category="query", ...)
5. Pattern-match error string against known patterns:
   a. SQL keywords (syntax, parse, column, table) → "query"
   b. Join/FK keywords (join, foreign key, mismatch) → "join-key"
   c. DB-type keywords (unsupported, wrong database, timeout, refused) → "db-type"
   d. Data keywords (empty, null, encoding, format) → "data-quality"
6. Default fallback: "query" (most common failure type)
7. Generate explanation and suggested_fix based on category
8. Return FailureDiagnosis
```

### Invariant (PBT-03)
`classify()` ALWAYS returns a FailureDiagnosis with `category` in `{"query", "join-key", "db-type", "data-quality"}`. Never raises, never returns None.

---

## Module: duckdb_bridge_client.py — DuckDB Bridge Wire Protocol (FR-03b)

### Responsibilities
- Speak the custom DuckDB MCP bridge wire protocol
- Schema discovery: `GET {DUCKDB_BRIDGE_URL}/tools`
- Query execution: `POST {DUCKDB_BRIDGE_URL}/invoke`
- Timeout enforcement: `DUCKDB_BRIDGE_TIMEOUT_SECONDS`
- Offline stub support

### Visibility
**PRIVATE** — imported ONLY by `mcp_toolbox_client.py`. No other module references this.

### Public API (within U2 only)

**`DuckDBBridgeClient`** class:
- `__init__(self)` — reads config; does NOT connect at init
- `discover_tools(self) -> list[ToolDescriptor]` — GET /tools
- `invoke(self, tool_name: str, params: dict) -> InvokeResult` — POST /invoke

### Algorithm: discover_tools
```
1. If AGENT_OFFLINE_MODE: return stub ToolDescriptor for query_duckdb from OFFLINE_TOOL_LIST
2. GET {DUCKDB_BRIDGE_URL}/tools with timeout=DUCKDB_BRIDGE_TIMEOUT_SECONDS
3. Parse JSON response as list of tool descriptors
4. Convert each to ToolDescriptor(name, kind="duckdb_bridge_sql", source="duckdb_bridge", ...)
5. Return list
```

### Algorithm: invoke
```
1. If AGENT_OFFLINE_MODE: return InvokeResult from OFFLINE_INVOKE_RESULTS["duckdb"]
2. Validate sql param length <= SANDBOX_MAX_PAYLOAD_CHARS (SEC-05)
3. POST {DUCKDB_BRIDGE_URL}/invoke with body: {"tool": tool_name, "parameters": {"sql": sql}}
4. Timeout: DUCKDB_BRIDGE_TIMEOUT_SECONDS
5. Parse response JSON: {success, result, error, error_type}
6. Return InvokeResult(success=resp.success, result=resp.result, error=resp.error, 
                        error_type=resp.error_type, tool_name=tool_name, db_type="duckdb")
```

### Error Handling (SEC-15)
- `requests.Timeout` → InvokeResult(success=False, error="timeout", error_type="timeout", db_type="duckdb")
- `requests.ConnectionError` → InvokeResult(success=False, error="connection_refused", error_type="config", db_type="duckdb")
- `json.JSONDecodeError` → InvokeResult(success=False, error="invalid_response", error_type="config", db_type="duckdb")

---

## Module: mcp_toolbox_client.py — Unified MCPClient Facade (FR-03)

### Responsibilities
- Read `tools.yaml` at init to build the 4-tool registry
- Single public interface: `discover_tools()` + `invoke_tool()`
- Internal dispatch by `kind` field — invisible to callers
- Standard kinds → Google MCP Toolbox; `duckdb_bridge_sql` → DuckDBBridgeClient
- Offline stub support for all 4 DB types

### Public API

**`MCPClient`** class:
- `__init__(self)` — loads tools.yaml, builds registry, creates DuckDBBridgeClient instance
- `discover_tools(self) -> list[ToolDescriptor]` — returns all 4 tools from registry
- `invoke_tool(self, tool_name: str, params: dict) -> InvokeResult` — dispatches by kind

### Algorithm: __init__
```
1. If AGENT_OFFLINE_MODE or not AGENT_USE_MCP:
   a. Build registry from OFFLINE_TOOL_LIST (4 tools)
   b. Create DuckDBBridgeClient() (will also use offline stubs)
   c. Return
2. Load tools.yaml from TOOLS_YAML_PATH
3. Parse YAML: extract sources{} and tools{}
4. For each tool entry:
   a. Create ToolDescriptor(name, kind, source, description)
   b. Add to internal _registry dict keyed by name
5. Create DuckDBBridgeClient() for duckdb_bridge_sql dispatch
```

### Algorithm: discover_tools
```
1. Return list(_registry.values()) — all 4 tools, no backend queried
```

### Algorithm: invoke_tool
```
1. Look up tool in _registry by name
2. If not found: return InvokeResult(success=False, error="unknown_tool", tool_name=name)
3. If AGENT_OFFLINE_MODE:
   a. Determine db_type from kind via db_type_from_kind()
   b. Return InvokeResult from OFFLINE_INVOKE_RESULTS[db_type]
4. Inspect tool.kind:
   a. If kind in {"postgres-sql", "mongodb-aggregate", "sqlite-sql"}:
      → dispatch to _invoke_toolbox(tool, params)
   b. If kind == "duckdb_bridge_sql":
      → dispatch to self._bridge.invoke(tool.name, params)
   c. Else: return InvokeResult(success=False, error="unsupported_kind")
5. Return InvokeResult
```

### Algorithm: _invoke_toolbox (private, Google MCP Toolbox)
```
1. POST {MCP_TOOLBOX_URL}/api/tool/{tool.name}/invoke with params
2. Timeout: MCP_TIMEOUT_SECONDS
3. Parse response; convert to InvokeResult
4. On error: return InvokeResult(success=False, error=str(exc), db_type=db_type)
```

### Dispatch Invariant (PBT-03)
Any tool with `kind == "duckdb_bridge_sql"` is ALWAYS dispatched to DuckDBBridgeClient.
Any tool with `kind in {"postgres-sql", "mongodb-aggregate", "sqlite-sql"}` is NEVER sent to DuckDBBridgeClient.
