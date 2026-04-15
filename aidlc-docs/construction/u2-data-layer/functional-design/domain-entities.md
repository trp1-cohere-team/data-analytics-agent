# Domain Entities — U2 Data Layer

## Overview
U2 does not define new dataclasses — it consumes entities from U1 `types.py`. This document maps which entities each U2 module uses.

---

## Entity Usage by Module

### knowledge_base.py
| Entity | Usage |
|---|---|
| (none from types.py) | Returns `list[tuple[str, float]]` — (doc_content, relevance_score) |

**Internal types** (not in types.py — local to module):
- `KBDocument`: `namedtuple("KBDocument", ["path", "content", "category"])` — loaded KB file

### context_layering.py
| Entity | Usage |
|---|---|
| `ContextPacket` | Output — composed 6-layer context |
| `LayerContent` | Input — individual layer data to compose |

### failure_diagnostics.py
| Entity | Usage |
|---|---|
| `FailureDiagnosis` | Output — classified failure with category, explanation, suggested fix |

### duckdb_bridge_client.py (private)
| Entity | Usage |
|---|---|
| `InvokeResult` | Output — unified result from DuckDB bridge call |
| `ToolDescriptor` | Output — tool descriptor from bridge schema discovery |

### mcp_toolbox_client.py (public facade)
| Entity | Usage |
|---|---|
| `ToolDescriptor` | Output — from `discover_tools()` |
| `InvokeResult` | Output — from `invoke_tool()` |

---

## Visibility Contract (from unit-of-work-dependency.md)

| Module | Public API | May Be Imported By |
|---|---|---|
| `knowledge_base.py` | `load_layered_kb_context()` | U3 |
| `context_layering.py` | `build_context_packet()`, `LayeredContext` | U3, U4 |
| `failure_diagnostics.py` | `classify()` | U3 |
| `mcp_toolbox_client.py` | `MCPClient` | U3, U4, U5 (tests) |
| `duckdb_bridge_client.py` | `DuckDBBridgeClient` | **mcp_toolbox_client.py ONLY** |
