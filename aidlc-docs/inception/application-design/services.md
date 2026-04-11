# Services
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Note**: Services define cross-cutting coordination flows that span multiple components.

---

## Service Map

```
SERVICE LAYER
  QueryService          — Orchestrates full query lifecycle (API → Orchestrator → Response)
  ContextService        — Manages three-layer context assembly per session
  CorrectionService     — Coordinates failure classification → fix strategy → retry
  ExecutionService      — Routes and fans-out sub-queries, resolves join keys, merges
  EvaluationService     — Coordinates benchmark runs, scoring, and score log updates
  KBMaintenanceService  — Handles KB writes: corrections append + changelog update
```

---

## Service 1: QueryService

**Coordinates**: AgentAPI → Orchestrator → ContextManager → MultiDBEngine → CorrectionEngine → AgentAPI

### Flow

```
[Client HTTP POST /query]
        |
        v
AgentAPI.handle_query()
  1. Validate QueryRequest (Pydantic)
  2. Generate session_id (UUID4)
  3. Call ContextService.get_bundle(session_id)
        |
        v
ContextService.get_bundle()
  - Layer 1: from permanent cache (schema)
  - Layer 2: from hot cache (reload if stale)
  - Layer 3: fresh read (corrections.json)
  Returns: ContextBundle
        |
        v
Orchestrator.run(query, session_id, context_bundle)
  ReAct loop (max 10 iterations):
    think() → LLM call → Thought
    act()   → tool dispatch → Observation
      [if DB query: ExecutionService.execute(sub_query)]
      [if failure: CorrectionService.correct(failure)]
    observe() → update ReactState
  Terminates: FINAL_ANSWER or max_iterations
  Returns: OrchestratorResult
        |
        v
AgentAPI.handle_query()
  - Build QueryResponse from OrchestratorResult
  - Return HTTP 200 with {answer, query_trace, confidence, session_id}
```

### Error Policy
- Any unhandled exception → HTTP 500 with `{"error": "query_failed", "message": "..."}` (no stack trace)
- `CorrectionExhausted` → HTTP 200 with low-confidence answer + error flag in trace
- Rate limit exceeded → HTTP 429 (slowapi)

---

## Service 2: ContextService

**Coordinates**: ContextManager → KnowledgeBase → SchemaIntrospector → MemoryManager

### Flow

```
Server Startup:
  SchemaIntrospector.introspect_all(mcp_toolbox_url)
    → introspect_postgres / introspect_sqlite / introspect_mongodb / introspect_duckdb
    → SchemaContext
  ContextManager._layer1_cache = SchemaContext    [permanent, never evicted]

  asyncio background task (every 60s):
    ContextManager._refresh_layer2_if_stale()
      → check file mtimes in kb/architecture/, kb/domain/
      → if changed: KnowledgeBase.get_architecture_docs() + get_domain_docs()
      → update ContextManager._layer2_cache

Per-Session (at Orchestrator.run() start):
  ContextManager.get_context_bundle(session_id)
    Layer 1: return _layer1_cache directly
    Layer 2: return _layer2_cache (already refreshed by background task)
    Layer 3: KnowledgeBase.get_corrections(limit=50)
             + MemoryManager.load_session_memory(session_id)
             → CorrectionsContext
    Returns: ContextBundle(schema_ctx, domain_ctx, corrections_ctx)
```

### Cache Lifecycle

| Layer | Populated At | Evicted/Refreshed | Scope |
|---|---|---|---|
| 1 — Schema | Server startup | Never | Process-global |
| 2 — Domain KB | Server startup + background | On file mtime change | Process-global |
| 3 — Corrections | Per session | After session ends | Session-scoped |

---

## Service 3: CorrectionService

**Coordinates**: CorrectionEngine → MultiDBEngine → KnowledgeBase (corrections append)

### Flow

```
Orchestrator detects ExecutionFailure from MultiDBEngine
        |
        v
CorrectionService.correct(failure, original_query, context, attempt)
  if attempt > 3: raise CorrectionExhausted
        |
        v
CorrectionEngine.classify_failure(failure) → FailureType
        |
   [branch on FailureType]
        |
   SYNTAX_ERROR ──────────→ fix_syntax_error(query, error) → corrected_query
   JOIN_KEY_MISMATCH ─────→ fix_join_key(query, mismatch) → corrected_query
   WRONG_DB_TYPE ─────────→ fix_wrong_db_type(plan, error) → corrected_plan
   DATA_QUALITY ──────────→ fix_data_quality(query, error) → corrected_query
   UNKNOWN ───────────────→ llm_correct(query, error, context) → corrected_query
        |
        v
ExecutionService.execute(corrected_query or corrected_plan)
  [success] → return CorrectionResult(success=True, corrected_query, result)
  [failure] → recurse: CorrectionService.correct(..., attempt=attempt+1)
        |
        v
KBMaintenanceService.append_correction(CorrectionEntry)
  - Always logged regardless of outcome
```

### Retry Policy
- Attempts: 1, 2, 3 (then `CorrectionExhausted`)
- No delay between attempts (failures are structural, not transient)
- LLM corrector only on attempt 3 if all rule-based strategies exhausted on previous attempts

---

## Service 4: ExecutionService

**Coordinates**: MultiDBEngine → MCP Toolbox (HTTP) → JoinKeyUtils → ResultMerger

### Flow

```
Orchestrator.act() receives tool_call: query_database
        |
        v
ExecutionService.execute(QueryPlan)
        |
        v
MultiDBEngine.execute_plan(plan)
  1. resolve_join_keys(plan)
       → JoinKeyUtils.detect_format(key_sample)
       → JoinKeyUtils.build_transform_expression(...)
       → rewrites JOIN conditions in place
  2. Fan-out sub-queries (asyncio.gather):
       route_and_execute(sub_query) for each sub_query
         → execute_postgres(query, params)  → MCP Toolbox HTTP POST /v1/tools/postgres_query
         → execute_sqlite(query, params)   → MCP Toolbox HTTP POST /v1/tools/sqlite_query
         → execute_mongodb(pipeline, coll) → MCP Toolbox HTTP POST /v1/tools/mongodb_aggregate
         → execute_duckdb(query, params)   → MCP Toolbox HTTP POST /v1/tools/duckdb_query
  3. merge_results(results, merge_spec)
       → join / union / aggregate as specified
  Returns: ExecutionResult or ExecutionFailure
```

### MCP Toolbox Protocol
- Base URL: `http://localhost:5000/v1/tools/{tool_name}`
- Method: HTTP POST, JSON body
- Auth: None (localhost only)
- Timeout: 30s per sub-query
- Errors: Returned as `ExecutionFailure` (never raised to API)

---

## Service 5: EvaluationService

**Coordinates**: EvaluationHarness → AgentAPI → ScoreLog → QueryTraceRecorder

### Flow

```
CLI: python -m eval.run_benchmark --trials 50
        |
        v
EvaluationService.run(agent_url, queries, n_trials, output_path)
        |
        v
EvaluationHarness.run_benchmark(...)
  For each query in DABQuerySet:
    For trial in range(n_trials):
      HTTP POST agent_url/query → result
      score_exact_match(result, expected)
      score_llm_judge(result, expected, question)  [if exact match fails]
      record_trace(session_id, trace)
    → per_query_scores
  aggregate → BenchmarkResult
        |
        v
ScoreLog.append(BenchmarkResult)  [append to results/score_log.jsonl]
        |
        v
[optional] RegressionSuite.run(agent_url, held_out_path)
  → assert pass@1 >= previous_run_score
```

### Scoring Policy
- Primary scorer: `score_exact_match` (tolerance 1e-4 for floats, normalized strings)
- Secondary scorer: `score_llm_judge` (GPT-4o judge; called only when exact match fails)
- Final pass@1 = fraction of queries with at least 1 passing trial in N
- Score log: append-only JSON Lines — never overwritten

---

## Service 6: KBMaintenanceService

**Coordinates**: KnowledgeBase → MemoryManager → CorrectionEngine (consumer)

### Flow

```
After any correction attempt (success or failure):
  KBMaintenanceService.append_correction(entry: CorrectionEntry)
        |
        v
  KnowledgeBase.append_correction(entry)
    → read corrections.json
    → append entry (JSON object per line)
    → write corrections.json
    → update_changelog("corrections", summary_line)
        |
        v
  [Next session start]
  ContextManager._load_layer3() picks up new correction automatically
  (Layer 3 is always fresh — no stale cache issue)

After session ends:
  MemoryManager.write_session_transcript(session_id, transcript)
  [After 7 days]
  MemoryManager.consolidate_old_sessions(max_age_days=7)
    → extract patterns from old sessions
    → merge into topics/successful_patterns.json
    → delete raw session files
```

### Write Safety
- `corrections.json`: append-only — never truncate or overwrite
- CHANGELOG.md files: append-only — one line per entry
- Session transcripts: one file per session_id — never modified after write
- No locking needed: single-process server, single writer at a time
