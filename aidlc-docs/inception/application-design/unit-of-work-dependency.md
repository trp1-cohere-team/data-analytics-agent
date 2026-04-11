# Unit of Work Dependency
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Construction Order**: U5 → U2 → U1 → U3 → U4

---

## Unit Dependency Matrix

| Depends On →  | Shared Infra | U5 Utilities | U2 MultiDB | U1 Agent Core | U3 KB/Memory | U4 Eval |
|---|---|---|---|---|---|---|
| **Shared Infra** | — | — | — | — | — | — |
| **U5 Utilities** | IMPORTS | — | — | — | — | — |
| **U2 MultiDB** | IMPORTS | IMPORTS | — | — | — | — |
| **U1 Agent Core** | IMPORTS | IMPORTS | IMPORTS | — | IMPORTS | — |
| **U3 KB/Memory** | IMPORTS | — | — | — | — | — |
| **U4 Eval** | IMPORTS | — | — | HTTP CALLS | — | — |

**Legend**: IMPORTS = Python import dependency | HTTP CALLS = runtime HTTP only (no import)

---

## Dependency Detail

### Shared Infrastructure → All Units
| Artifact | Used By | What Is Imported |
|---|---|---|
| `agent/models.py` | U1, U2, U3, U4, U5 | All shared Pydantic models and dataclasses |
| `agent/config.py` | U1, U2, U3, U5 | Settings instance (API keys, URLs, thresholds) |

### U5 → U2
| From (U5) | To (U2) | What |
|---|---|---|
| `utils/join_key_utils.py` | `agent/execution/engine.py` | `detect_format()`, `build_transform_expression()`, `transform_key()` |

### U5 → U1
| From (U5) | To (U1) | What |
|---|---|---|
| `utils/schema_introspector.py` | `agent/context/manager.py` | `introspect_all()` (at startup) |
| `utils/multi_pass_retriever.py` | `agent/orchestrator/react_loop.py` | `retrieve_corrections()` (search_kb tool) |
| `utils/join_key_utils.py` | `agent/orchestrator/react_loop.py` | `detect_format()`, `build_transform_expression()` (resolve_join_keys tool) |

### U2 → U1
| From (U2) | To (U1) | What |
|---|---|---|
| `agent/execution/engine.py` | `agent/orchestrator/react_loop.py` | `execute_plan()` (query_database tool dispatch) |

### U3 → U1
| From (U3) | To (U1) | What |
|---|---|---|
| `agent/kb/knowledge_base.py` | `agent/context/manager.py` | `get_architecture_docs()`, `get_domain_docs()`, `get_corrections()`, `append_correction()` |
| `agent/memory/manager.py` | `agent/context/manager.py` | `load_session_memory()` |
| `agent/memory/manager.py` | `agent/orchestrator/react_loop.py` | `write_session_transcript()` |

### U1 → U4 (runtime HTTP only, no import)
| From (U4) | To (U1) | What |
|---|---|---|
| `eval/harness.py` | `agent/api/app.py` | HTTP POST `/query` — EvaluationHarness treats agent as black box |

---

## Build Order Graph

```
[Shared Infra]
  agent/models.py
  agent/config.py
  tests/ structure
       │
       ▼
  [U5 — Utilities]          ← Build first: no unit dependencies
  utils/schema_introspector.py
  utils/multi_pass_retriever.py
  utils/join_key_utils.py
  utils/benchmark_wrapper.py
  probes/probe_runner.py
       │
       ▼
  [U2 — MultiDB Engine]     ← Needs: JoinKeyUtils (U5)
  agent/execution/engine.py
  agent/execution/mcp_client.py
       │
       ▼
  [U3 — KB & Memory]        ← Independent; built here to unblock U1
  agent/kb/knowledge_base.py
  agent/memory/manager.py
       │
       ▼
  [U1 — Agent Core & API]   ← Needs: U2 (execute_plan), U3 (KB/Memory), U5 (introspector, retriever)
  agent/api/app.py
  agent/api/middleware.py
  agent/orchestrator/react_loop.py
  agent/context/manager.py
  agent/correction/engine.py
       │
       ▼
  [U4 — Evaluation Harness] ← Needs: U1 running (HTTP); no import dependency
  eval/harness.py
  eval/run_benchmark.py
       │
       ▼
  [Integration Tests]       ← Needs: all units + MCP Toolbox process
  tests/integration/
```

---

## Interface Contracts (agreed before construction)

These interfaces must be stable before downstream units are built:

| Interface | Defined In | Used By | Contract |
|---|---|---|---|
| `MultiDBEngine.execute_plan(QueryPlan) → ExecutionResult \| ExecutionFailure` | U2 | U1 (Orchestrator) | Async; never raises; always returns typed result |
| `KnowledgeBase.get_corrections(limit) → list[CorrectionEntry]` | U3 | U1 (ContextManager) | Synchronous; reads file; never raises |
| `KnowledgeBase.append_correction(CorrectionEntry) → None` | U3 | U1 (CorrectionEngine) | Synchronous; file append; never raises |
| `MemoryManager.load_session_memory(session_id) → SessionMemory` | U3 | U1 (ContextManager) | Synchronous; returns empty SessionMemory if no file |
| `JoinKeyUtils.detect_format(key_sample) → JoinKeyFormat` | U5 | U2, U1 | Pure function; no side effects |
| `SchemaIntrospector.introspect_all(url) → SchemaContext` | U5 | U1 (ContextManager) | Async; returns empty SchemaContext on MCP Toolbox unavailability |
| `MultiPassRetriever.retrieve_corrections(query, corrections) → list[CorrectionEntry]` | U5 | U1 (Orchestrator) | Synchronous; pure function |

---

## Risk Register

| Risk | Units Affected | Mitigation |
|---|---|---|
| MCP Toolbox unavailable during development | U2, U5 | Mock MCP Toolbox responses in unit tests; integration tests require MCP Toolbox |
| OpenRouter rate limit during evaluation | U1, U4 | Exponential backoff (max 3 retries); LLM judge batched |
| `corrections.json` grows unbounded | U3 | `get_corrections(limit=50)` cap; Memory consolidation after 7 days |
| Cross-unit model drift (models.py changes) | All | `agent/models.py` is single source of truth; any change requires review of all callers |
| U1 build blocked waiting on U3 interfaces | U1, U3 | U3 interface contracts locked before U1 code generation begins |
