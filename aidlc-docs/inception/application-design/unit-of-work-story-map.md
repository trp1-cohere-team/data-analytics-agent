# Unit of Work Story Map
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Note**: User Stories stage was skipped (technical challenge, no user personas). This document maps requirements (FR/NFR) and components to units instead.

---

## Requirements-to-Unit Map

| Requirement | Description | Unit |
|---|---|---|
| FR-01 | NL query interface: POST /query → {answer, query_trace, confidence} | U1 |
| FR-02 | All 4 DB types (PostgreSQL, SQLite, MongoDB, DuckDB) via MCP Toolbox | U2 |
| FR-03 | Three-layer context: schema (permanent cache) / KB (file-watch) / corrections (per-session) | U1 + U3 |
| FR-04 | Self-correcting execution loop (≥3 recovery attempts, failure diagnosis by type) | U1 (CorrectionEngine) |
| FR-05 | Join key resolution (cross-DB entity key format mismatch detection + transformation) | U2 + U5 |
| FR-06 | Unstructured text extraction via LLM sub-call | U1 (Orchestrator) |
| FR-07 | Evaluation harness: pass@1 + LLM-as-judge, query trace, score log | U4 |
| FR-08 | KB with 4 subdirs (architecture, domain, evaluation, corrections) + CHANGELOG + injection tests | U3 |
| FR-09 | ≥15 adversarial probes, ≥3 failure categories | U5 (ProbeLibrary) |
| FR-10 | Repository structure: agent/, kb/, eval/, planning/, utils/, signal/, probes/, results/ | All units |
| FR-11 | MCP Toolbox integration (tools.yaml, HTTP calls) | U2 + U5 |
| NFR-01 | ReAct loop (max 10 iterations, confidence threshold 0.85) | U1 (Orchestrator) |
| NFR-02 | OpenRouter → GPT-4o (async, max 3 retries with backoff) | U1 |
| NFR-03 | MEMORY.md pattern (JSON session files, autoDream consolidation after 7 days) | U3 (MemoryManager) |
| NFR-04 | Security baseline: 15 blocking rules (encryption, headers, rate limit, validation, etc.) | U1 (AgentAPI) |
| NFR-05 | Property-Based Testing: Hypothesis framework, round-trip/invariant/idempotency tests | U5 (JoinKeyUtils), U1 (CorrectionEngine), U2 |

---

## Component-to-Unit Map

| Component | Unit | File |
|---|---|---|
| AgentAPI | U1 | `agent/api/app.py` |
| Orchestrator | U1 | `agent/orchestrator/react_loop.py` |
| ContextManager | U1 | `agent/context/manager.py` |
| CorrectionEngine | U1 | `agent/correction/engine.py` |
| MultiDBEngine | U2 | `agent/execution/engine.py` |
| QueryRouter | U2 | internal to `engine.py` |
| PostgreSQLConnector | U2 | internal to `engine.py` |
| SQLiteConnector | U2 | internal to `engine.py` |
| MongoDBConnector | U2 | internal to `engine.py` |
| DuckDBConnector | U2 | internal to `engine.py` |
| JoinKeyResolver | U2 | internal to `engine.py` (delegates to U5 JoinKeyUtils) |
| ResultMerger | U2 | internal to `engine.py` |
| KnowledgeBase | U3 | `agent/kb/knowledge_base.py` |
| MemoryManager | U3 | `agent/memory/manager.py` |
| EvaluationHarness | U4 | `eval/harness.py` |
| BenchmarkRunner | U4 | internal to `harness.py` |
| ExactMatchScorer | U4 | internal to `harness.py` |
| LLMJudgeScorer | U4 | internal to `harness.py` |
| QueryTraceRecorder | U4 | internal to `harness.py` |
| RegressionSuite | U4 | internal to `harness.py` |
| ScoreLog | U4 | internal to `harness.py` |
| SchemaIntrospector | U5 | `utils/schema_introspector.py` |
| MultiPassRetriever | U5 | `utils/multi_pass_retriever.py` |
| JoinKeyUtils | U5 | `utils/join_key_utils.py` |
| BenchmarkWrapper | U5 | `utils/benchmark_wrapper.py` |
| ProbeLibrary | U5 | `probes/probes.md` + `probes/probe_runner.py` |

---

## Shared Infrastructure Map

| Artifact | Owns | Consumed By |
|---|---|---|
| `agent/models.py` | Shared (no unit owner) | U1, U2, U3, U4, U5 |
| `agent/config.py` | Shared (no unit owner) | U1, U2, U3, U5 |
| `tools.yaml` | Infrastructure (no unit owner) | MCP Toolbox process (external) |
| `planning/AGENT.md` | Documentation | Developer reference |
| `tests/integration/` | Cross-unit | All units |

---

## Coverage Verification

| Unit | FR Coverage | NFR Coverage | All Components Assigned |
|---|---|---|---|
| U1 — Agent Core & API | FR-01, FR-03, FR-04, FR-06 + NFR-01, NFR-02, NFR-04 | Security (15 rules), ReAct loop | AgentAPI, Orchestrator, ContextManager, CorrectionEngine |
| U2 — Multi-DB Execution Engine | FR-02, FR-05, FR-11 | Async execution, error wrapping | MultiDBEngine + all 6 sub-components |
| U3 — Knowledge Base & Memory | FR-03 (layer 2+3), FR-08 + NFR-03 | File integrity, append-only writes | KnowledgeBase, MemoryManager |
| U4 — Evaluation Harness | FR-07 | Score log integrity, regression guard | EvaluationHarness + all 6 sub-components |
| U5 — Utilities & Probes | FR-05, FR-09, FR-11 + NFR-05 | PBT (JoinKeyUtils, SchemaIntrospector) | SchemaIntrospector, MultiPassRetriever, JoinKeyUtils, BenchmarkWrapper, ProbeLibrary |

**All 11 FRs covered**: FR-01 ✓ FR-02 ✓ FR-03 ✓ FR-04 ✓ FR-05 ✓ FR-06 ✓ FR-07 ✓ FR-08 ✓ FR-09 ✓ FR-10 ✓ FR-11 ✓  
**All 5 NFRs covered**: NFR-01 ✓ NFR-02 ✓ NFR-03 ✓ NFR-04 ✓ NFR-05 ✓  
**All 25 components assigned**: ✓
