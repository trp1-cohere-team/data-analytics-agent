# Component Dependency
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Note**: Arrows indicate runtime call direction (caller → callee). Static imports not shown.

---

## Dependency Matrix

| Caller \ Callee | AgentAPI | Orchestrator | ContextManager | CorrectionEngine | MultiDBEngine | KnowledgeBase | MemoryManager | EvaluationHarness | SchemaIntrospector | MultiPassRetriever | JoinKeyUtils | MCP Toolbox |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **AgentAPI** | — | CALLS | CALLS | — | — | — | — | — | — | — | — | — |
| **Orchestrator** | — | — | CALLS | CALLS | CALLS | — | CALLS | — | — | — | — | — |
| **ContextManager** | — | — | — | — | — | CALLS | CALLS | — | CALLS | — | — | — |
| **CorrectionEngine** | — | — | — | — | CALLS | CALLS | — | — | — | — | CALLS | — |
| **MultiDBEngine** | — | — | — | — | — | — | — | — | — | — | CALLS | CALLS |
| **KnowledgeBase** | — | — | — | — | — | — | — | — | — | — | — | — |
| **MemoryManager** | — | — | — | — | — | — | — | — | — | — | — | — |
| **EvaluationHarness** | CALLS | — | — | — | — | CALLS | — | — | — | — | — | — |
| **SchemaIntrospector** | — | — | — | — | — | — | — | — | — | — | — | CALLS |
| **MultiPassRetriever** | — | — | — | — | — | — | — | — | — | — | — | — |
| **JoinKeyUtils** | — | — | — | — | — | — | — | — | — | — | — | — |

**Legend**: CALLS = runtime dependency (caller invokes callee at runtime). — = no dependency.

---

## Dependency Graph (ASCII)

```
External Clients
      |
      | HTTP
      v
[AgentAPI]──────────────────────────────────┐
      |                                     |
      | run(query, session_id, context)     | startup_load()
      v                                     v
[Orchestrator]                     [ContextManager]────────[SchemaIntrospector]──→ MCP Toolbox
      |                                     |                                        (HTTP)
      |──think/act/observe loop             |────[KnowledgeBase] (read Layer 2+3)
      |                                     |────[MemoryManager] (read Layer 3 memory)
      |
      |─── query_database tool ────────────→[MultiDBEngine]
      |                                          |─── execute_postgres ──→ MCP Toolbox
      |                                          |─── execute_sqlite   ──→ MCP Toolbox
      |                                          |─── execute_mongodb  ──→ MCP Toolbox
      |                                          |─── execute_duckdb   ──→ MCP Toolbox
      |                                          |─── resolve_join_keys──→[JoinKeyUtils]
      |
      |─── on failure ─────────────────────→[CorrectionEngine]
      |                                          |─── classify_failure
      |                                          |─── fix_syntax_error (rule-based)
      |                                          |─── fix_join_key ────→[JoinKeyUtils]
      |                                          |─── fix_wrong_db_type
      |                                          |─── fix_data_quality
      |                                          |─── llm_correct ────→ OpenRouter (HTTP)
      |                                          |─── append_correction→[KnowledgeBase]
      |
      |─── write_transcript ───────────────→[MemoryManager]
      |
      └─── _call_llm ──────────────────────→ OpenRouter (HTTP)


[EvaluationHarness]──────────────────────────→[AgentAPI] (HTTP /query)
      |
      |────[KnowledgeBase] (read evaluation docs)
      |────[ScoreLog] (append results/score_log.jsonl)
      |────[QueryTraceRecorder] (write results/traces/)


[MultiPassRetriever] ← used by Orchestrator (search_kb tool) to rank corrections
```

---

## Data Flow: Query Lifecycle

```
Step  From                To                    Data
────  ────────────────────────────────────────────────────────────────────
1     Client              AgentAPI              QueryRequest(question, databases, session_id)
2     AgentAPI            ContextManager        session_id
3     ContextManager      SchemaIntrospector    mcp_toolbox_url  [startup only]
4     ContextManager      KnowledgeBase         (read) Layer 2 docs
5     ContextManager      MemoryManager         session_id  [read Layer 3 memory]
6     ContextManager      AgentAPI              ContextBundle(schema, domain, corrections)
7     AgentAPI            Orchestrator          query, session_id, ContextBundle
8     Orchestrator        LLM (OpenRouter)      messages[], tools[]
9     LLM                 Orchestrator          Thought(reasoning, action, action_input)
10    Orchestrator        MultiDBEngine         QueryPlan(sub_queries, merge_spec)
11    MultiDBEngine       JoinKeyUtils          key_sample  [detect + transform]
12    MultiDBEngine       MCP Toolbox (HTTP)    tool_name, query/pipeline, params
13    MCP Toolbox         MultiDBEngine         SubQueryResult(rows, columns, error)
14    MultiDBEngine       Orchestrator          ExecutionResult or ExecutionFailure
15a   [success] Orchestrator  LLM             Observation → next think step
15b   [failure] Orchestrator  CorrectionEngine  ExecutionFailure, original_query, ContextBundle
16    CorrectionEngine    KnowledgeBase         CorrectionEntry (append)
17    CorrectionEngine    MultiDBEngine         corrected QueryPlan
18    Orchestrator        Orchestrator          ReactState update (observe step)
19    Orchestrator        MemoryManager         session_id, QueryTrace (write transcript)
20    Orchestrator        AgentAPI              OrchestratorResult(answer, trace, confidence)
21    AgentAPI            Client                QueryResponse(answer, query_trace, confidence, session_id)
```

---

## Data Flow: Server Startup

```
Step  From                To                    Data
────  ────────────────────────────────────────────────────────────────────
1     Process start       ContextManager        startup_load() call
2     ContextManager      SchemaIntrospector    introspect_all(mcp_toolbox_url)
3     SchemaIntrospector  MCP Toolbox (HTTP)    introspect_{postgres,sqlite,mongodb,duckdb}
4     SchemaIntrospector  ContextManager        SchemaContext (Layer 1)
5     ContextManager      KnowledgeBase         get_architecture_docs(), get_domain_docs()
6     KnowledgeBase       ContextManager        list[KBDocument] (Layer 2 initial load)
7     ContextManager      asyncio               spawn _refresh_layer2_if_stale() background task
8     Server              Clients               Ready to accept requests
```

---

## Data Flow: Evaluation Run

```
Step  From                To                    Data
────  ────────────────────────────────────────────────────────────────────
1     CLI                 EvaluationHarness     agent_url, queries, n_trials
2     EvaluationHarness   AgentAPI (HTTP)       QueryRequest per trial
3     AgentAPI            EvaluationHarness     QueryResponse per trial
4     EvaluationHarness   ExactMatchScorer      result, expected
5     EvaluationHarness   LLMJudgeScorer        result, expected, question  [if exact fails]
6     LLMJudgeScorer      LLM (OpenRouter)      judge prompt
7     EvaluationHarness   QueryTraceRecorder    session_id, trace
8     EvaluationHarness   ScoreLog              BenchmarkResult (append to score_log.jsonl)
9     EvaluationHarness   RegressionSuite       agent_url, held_out_path
```

---

## Coupling Analysis

### Tight Coupling (justified)
| Pair | Reason |
|---|---|
| Orchestrator ↔ CorrectionEngine | Same failure-handling transaction; must share ExecutionFailure type |
| MultiDBEngine ↔ JoinKeyUtils | JoinKeyUtils is a pure utility called inline; no indirection needed |
| ContextManager ↔ KnowledgeBase | ContextManager owns the cache; KnowledgeBase owns the files — clear split |

### Loose Coupling (by design)
| Pair | Mechanism | Reason |
|---|---|---|
| Agent ↔ MCP Toolbox | HTTP (localhost) | MCP Toolbox is a separate binary; protocol boundary enforces independence |
| Agent ↔ LLM | HTTP (OpenRouter) | LLM is a remote service; swappable by changing base_url + model |
| EvaluationHarness ↔ AgentAPI | HTTP /query | Eval can run against any agent instance; not coupled to internal state |
| CorrectionEngine ↔ LLM | Injected context only | LLM corrector receives only string + schema; no access to agent internals |

### No Dependency (deliberate isolation)
| Components | Reason for Isolation |
|---|---|
| MemoryManager ↔ KnowledgeBase | Different write domains: memory is session-scoped, KB is agent-wide |
| EvaluationHarness ↔ Orchestrator | Eval treats agent as black box; must not depend on internal state |
| MultiPassRetriever ↔ MultiDBEngine | Retriever is read-only over corrections; has no execution authority |

---

## Unit Boundary Summary

| Unit | Components Owned | External Interface |
|---|---|---|
| U1 — Agent Core & API | AgentAPI, Orchestrator, ContextManager, CorrectionEngine | HTTP /query, /health, /schema |
| U2 — Multi-DB Execution Engine | MultiDBEngine (all sub-components) | Called by Orchestrator; calls MCP Toolbox |
| U3 — Knowledge Base & Memory | KnowledgeBase, MemoryManager | File system only (kb/, agent/memory/) |
| U4 — Evaluation Harness | EvaluationHarness (all sub-components) | HTTP calls to AgentAPI; writes results/ |
| U5 — Utilities & Probes | SchemaIntrospector, MultiPassRetriever, JoinKeyUtils, ProbeLibrary | Used by U1, U2; no outbound except MCP Toolbox (SchemaIntrospector) |
