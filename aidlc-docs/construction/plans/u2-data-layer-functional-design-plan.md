# Functional Design Plan — U2 Data Layer

## Unit Context
- **Unit**: U2 — Data Layer
- **Purpose**: Knowledge retrieval, context construction, unified DB tool interface, and failure diagnosis
- **Modules**: `knowledge_base.py`, `context_layering.py`, `failure_diagnostics.py`, `duckdb_bridge_client.py` (private), `mcp_toolbox_client.py` (public facade)
- **Dependencies**: U1 (`types.py`, `config.py`, `text_utils.py`)

## Plan Steps

- [x] Step 1: Define knowledge_base.py business logic (KB retrieval with weighted ranking)
- [x] Step 2: Define context_layering.py business logic (6-layer composition with precedence)
- [x] Step 3: Define failure_diagnostics.py business logic (4-category classifier)
- [x] Step 4: Define duckdb_bridge_client.py business logic (private DuckDB bridge wire protocol)
- [x] Step 5: Define mcp_toolbox_client.py business logic (unified MCPClient facade)
- [x] Step 6: Identify PBT-01 testable properties for U2 components
- [x] Step 7: Generate functional design artifacts

## Questions Assessment
**No clarification questions required.** FR-02, FR-03, FR-03b, FR-04, FR-09, and the unit-of-work dependency map fully specify all module interfaces, dispatch logic, and offline behavior.
