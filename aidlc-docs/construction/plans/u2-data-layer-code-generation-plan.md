# Code Generation Plan — U2 Data Layer

## Unit Context
- **Unit**: U2 — Data Layer
- **Purpose**: Knowledge retrieval, context construction, unified DB tool interface, failure diagnosis
- **Functional Design**: `aidlc-docs/construction/u2-data-layer/functional-design/`
- **Dependencies**: U1 (types.py, config.py, text_utils.py)
- **Build order within U2**: duckdb_bridge_client.py BEFORE mcp_toolbox_client.py

## Requirement Traceability
| Step | Requirement(s) | Module |
|---|---|---|
| Step 1 | FR-09 | `agent/data_agent/knowledge_base.py` |
| Step 2 | FR-02 | `agent/data_agent/context_layering.py` |
| Step 3 | FR-04 | `agent/data_agent/failure_diagnostics.py` |
| Step 4 | FR-03b | `agent/data_agent/duckdb_bridge_client.py` |
| Step 5 | FR-03 | `agent/data_agent/mcp_toolbox_client.py` |

---

## Plan Steps

- [x] **Step 1: Generate `agent/data_agent/knowledge_base.py`**
  - `load_layered_kb_context(query, categories)` — weighted KB retrieval
  - Scoring: 0.6*content + 0.25*filename + 0.15*freshness
  - Safe file I/O with error handling (SEC-15)

- [x] **Step 2: Generate `agent/data_agent/context_layering.py`**
  - `build_context_packet()` — compose 6 layers into ContextPacket
  - `assemble_prompt()` — Layer 6→1 precedence ordering
  - Backward-compat aliases verified via ContextPacket properties

- [x] **Step 3: Generate `agent/data_agent/failure_diagnostics.py`**
  - `classify(error, context)` — pattern-matching → 4 categories
  - DuckDB error_type mapping; default fallback to "query"
  - Never raises, never returns None (PBT-03)

- [x] **Step 4: Generate `agent/data_agent/duckdb_bridge_client.py`**
  - `DuckDBBridgeClient` — GET /tools + POST /invoke
  - Timeout/connection error handling (SEC-15)
  - Offline stub support; SQL length validation (SEC-05)

- [x] **Step 5: Generate `agent/data_agent/mcp_toolbox_client.py`**
  - `MCPClient` — loads tools.yaml, dispatches by kind
  - Standard kinds → _invoke_toolbox(); duckdb_bridge_sql → DuckDBBridgeClient
  - Offline mode returns stubs for all 4 DB types

- [x] **Step 6: Generate code summary documentation**
  - `aidlc-docs/construction/u2-data-layer/code/code-summary.md`

## Total Steps: 6
