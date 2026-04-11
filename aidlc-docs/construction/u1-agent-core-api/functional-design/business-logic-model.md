# Business Logic Model
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API

---

## 1. AgentAPI — Request Pipeline

```
POST /query
  ↓
[1] Validate QueryRequest (Pydantic — length, type)
  ↓
[2] Resolve session_id
    IF request.session_id provided → use as-is (Q11=B)
    ELSE → generate uuid4()
  ↓
[3] Assemble context bundle
    ContextManager.get_context_bundle(session_id)
  ↓
[4] Run Orchestrator
    Orchestrator.run(query, session_id, context_bundle)
  ↓
[5] Save session transcript (Q8=A)
    MemoryManager.save_session(session_id, result.query_trace, summary)
  ↓
[6] Return QueryResponse(answer, query_trace, confidence, session_id)

Errors:
  ValidationError → HTTP 422 (FastAPI default)
  Any unhandled exception → global error handler → HTTP 500 {"error": "query_failed", "message": "<sanitized>"}
  Never expose stack traces or internal details
```

### GET /health
```
[1] Probe MCP Toolbox reachability (probe_mcp_toolbox from U2)
[2] Return HealthResponse(status="ok"|"degraded", mcp_toolbox=bool, databases={})
    - status="ok" if mcp_toolbox=True
    - status="degraded" if mcp_toolbox=False
```

### GET /schema
```
[1] Read SchemaContext from ContextManager in-memory cache (no disk I/O)
[2] Return SchemaResponse(databases={db_name: {tables: [...]}})
```

---

## 2. ContextManager — Three-Layer Assembly

### Startup (Layer 1)
```
startup_load():
  [1] Call SchemaIntrospector.introspect_all() → SchemaContext
  [2] Store in self._schema_ctx (permanent in-memory cache)
  [3] Start asyncio background task: _refresh_layer2_if_stale() loop
```

### Per-Session Assembly
```
get_context_bundle(session_id):
  Layer 1: return self._schema_ctx (always from cache)

  Layer 2: (mtime-based — Q6=A)
    FOR each .md file in KB subdirs:
      IF file.stat().st_mtime > self._layer2_loaded_at:
        reload all docs → update self._domain_ctx and self._layer2_loaded_at
        BREAK (reload is all-or-nothing)
    RETURN self._domain_ctx

  Layer 3: (always fresh — Q7=B)
    corrections = KnowledgeBase.get_corrections(limit=settings.corrections_limit)
    topics = MemoryManager.get_topics()
    RETURN CorrectionsContext(corrections=corrections, session_memory=topics)

  RETURN ContextBundle(schema_ctx, domain_ctx, corrections_ctx)
```

### Background Layer 2 Refresh
```
_refresh_layer2_if_stale():  [runs every layer2_refresh_interval_s seconds]
  FOR each .md file in KB subdirs:
    IF file.stat().st_mtime > self._layer2_loaded_at:
      reload domain_ctx
      RETURN
```

### LLM Prompt Formatting for Layer 3
```
Markdown bullet per CorrectionEntry (Q7=B):
  "- [FAILURE_TYPE] `{original_query[:80]}...` → {fix_strategy}"
  (success=True entries weighted first; all N entries included regardless)
```

---

## 3. Orchestrator — ReAct Loop

### System Prompt Structure (Q1=B)
```
SYSTEM PROMPT contains:
  1. Role definition: "You are a data analytics agent..."
  2. Available actions (plain text list):
     - query_database: action_input = {QueryPlan JSON}
     - search_kb: action_input = {"query": str}
     - extract_from_text: action_input = {"text": str, "question": str}
     - resolve_join_keys: action_input = {"plan": QueryPlan JSON}
     - FINAL_ANSWER: action_input = {"answer": Any, "confidence": float}
  3. Schema context (Layer 1): all DB schemas
  4. Domain KB (Layer 2): document contents
  5. Corrections context (Layer 3): markdown bullet list
  6. Response format instruction:
     "Always respond with valid JSON: {"reasoning": str, "action": str, "action_input": {...}, "confidence": float}"
```

### run() — Main Loop
```
run(query, session_id, context, max_iterations=10, confidence_threshold=0.85):
  state = ReactState(query=query, session_id=session_id)
  
  WHILE NOT state.terminated AND state.iteration < max_iterations:
    thought = await think(state)           # LLM call → Thought
    observation = await act(thought, context)  # tool dispatch → Observation
    state = observe(observation, state)    # update state; check termination
    
    IF thought.chosen_action == "FINAL_ANSWER":
      state.terminated = True
      state.final_answer = thought.action_input.get("answer")
      state.confidence = thought.confidence
  
  IF NOT state.terminated:  # max_iterations reached without FINAL_ANSWER (Q2=C)
    return OrchestratorResult(
      answer="I could not answer this question within the iteration limit.",
      query_trace=state.history,
      confidence=0.0,
      session_id=session_id,
      iterations_used=max_iterations,
    )
  
  RETURN OrchestratorResult(
    answer=state.final_answer,
    query_trace=state.history,
    confidence=state.confidence,
    session_id=session_id,
    iterations_used=state.iteration,
  )
```

### think() — LLM Step
```
think(state):
  messages = build_messages(state)  # system prompt + conversation history
  raw = await _call_llm(messages, tools=[])  # tools=[] — no function-calling (Q1=B)
  parsed = json.loads(raw.content)  # {"reasoning", "action", "action_input", "confidence"}
  RETURN Thought(
    reasoning=parsed["reasoning"],
    chosen_action=parsed["action"],
    action_input=parsed["action_input"],
    confidence=parsed.get("confidence", 0.0),  # Q3=A: LLM-reported
  )
```

### act() — Tool Dispatch
```
act(thought, context):
  MATCH thought.chosen_action:
    "query_database":
      plan = QueryPlan(**thought.action_input)  # Q4=B: LLM provides full QueryPlan
      result = await MultiDBEngine.execute_plan(plan)
      IF result.failures:
        correction = await _handle_correction(result.failures[0], plan, context)
        IF correction.success:
          result = await MultiDBEngine.execute_plan(correction.corrected_plan)
      RETURN Observation(action="query_database", result=result.merged_rows, success=not result.failures)
    
    "search_kb":
      query = thought.action_input["query"]
      docs = await KnowledgeBase.load_documents("domain")
      relevant = MultiPassRetriever.retrieve(query, docs)
      RETURN Observation(action="search_kb", result=relevant, success=True)
    
    "extract_from_text":
      # Summarize/extract from a text blob using LLM
      answer = await _call_llm([extract_prompt], tools=[])
      RETURN Observation(action="extract_from_text", result=answer, success=True)
    
    "resolve_join_keys":
      plan = QueryPlan(**thought.action_input["plan"])
      resolved = JoinKeyResolver.pre_execute_resolve(plan)
      RETURN Observation(action="resolve_join_keys", result=resolved.model_dump(), success=True)
    
    "FINAL_ANSWER":
      RETURN Observation(action="FINAL_ANSWER", result=thought.action_input.get("answer"), success=True)
```

### _handle_correction() — CorrectionEngine Integration (Q5=B)
```
_handle_correction(failure, plan, context):
  correction = await CorrectionEngine.correct(failure, plan.sub_queries[0].query, context)
  IF correction.success:
    append CorrectionEntry to KnowledgeBase (success=True)
  ELSE:
    append CorrectionEntry to KnowledgeBase (success=False)
  # Loop back to think() with error observation — orchestrator does NOT re-execute directly
  RETURN correction
```

### _call_llm() — Rate-limit Retry
```
_call_llm(messages, tools, max_retries=3):
  FOR attempt IN range(max_retries):
    TRY:
      response = await openai_client.chat.completions.create(
        model=settings.openrouter_model,
        messages=messages,
      )
      RETURN response.choices[0].message
    EXCEPT RateLimitError:
      IF attempt < max_retries - 1:
        await asyncio.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s
      ELSE:
        RAISE
```

---

## 4. CorrectionEngine — Tiered Fix Strategies

```
correct(failure, original_query, context, attempt=1):
  IF attempt > settings.max_correction_attempts:
    RAISE CorrectionExhausted("Max correction attempts reached")
  
  failure_type = classify_failure(failure)
  
  MATCH failure_type:
    SYNTAX_ERROR:
      corrected = fix_syntax_error(original_query, failure.error_message)
      RETURN CorrectionResult(success=True, corrected_query=corrected, fix_strategy="rule_syntax", attempt_number=attempt)
    
    JOIN_KEY_MISMATCH:
      mismatch = detect_mismatch(failure)
      corrected = fix_join_key(original_query, mismatch)
      RETURN CorrectionResult(success=True, corrected_query=corrected, fix_strategy="rule_join_key", attempt_number=attempt)
    
    WRONG_DB_TYPE:
      corrected_plan = fix_wrong_db_type(plan, failure)
      RETURN CorrectionResult(success=True, corrected_plan=corrected_plan, fix_strategy="rule_db_type", attempt_number=attempt)
    
    DATA_QUALITY:
      corrected = fix_data_quality(original_query, failure)
      RETURN CorrectionResult(success=True, corrected_query=corrected, fix_strategy="rule_null_guard", attempt_number=attempt)
    
    UNKNOWN:
      corrected = await llm_correct(original_query, failure.error_message, context)
      RETURN CorrectionResult(success=True, corrected_query=corrected, fix_strategy="llm_corrector", attempt_number=attempt)
```

### classify_failure() — Rule-Based Classifier
```
classify_failure(failure: ExecutionFailure) -> FailureType:
  error = failure.error_message.lower()
  
  IF any syntax keyword in error (eg. "syntax error", "unexpected token", "near", "invalid syntax"):
    RETURN SYNTAX_ERROR
  
  IF "join" in error AND ("type mismatch" OR "no rows" OR "format"):
    RETURN JOIN_KEY_MISMATCH
  
  IF db_type mismatch detected: (Q10=B)
    known_patterns = {
      "postgres": ["psycopg", "pg_", "relation does not exist", "column ... does not exist"],
      "sqlite": ["no such table", "no such column", "sqlite"],
      "mongodb": ["$match", "aggregation", "bson"],
      "duckdb": ["catalog", "duckdb", "binder error"],
    }
    FOR db, patterns IN known_patterns:
      IF failure.db_type != db AND any pattern in error:
        RETURN WRONG_DB_TYPE
  
  IF "null" in error OR "none" in error OR "missing" in error OR "not found":
    RETURN DATA_QUALITY
  
  RETURN UNKNOWN
```

### fix_syntax_error() — Rule-Based Rewriter (Q9=C)
```
Handles:
  1. Missing quotes around string literals: WHERE name = value → WHERE name = 'value'
  2. GROUP BY without aggregate: SELECT col, col2 GROUP BY col → add COUNT(*) aggregate
  3. Wrong dialect keyword:
     - ROWNUM → LIMIT (SQLite/Postgres/DuckDB)
     - TOP N → LIMIT N
     - ISNULL() → IS NULL
     - NVL() → COALESCE()
```

### fix_wrong_db_type() — DB Rerouting (Q10=B)
```
Checks error_message against db_type error signal patterns.
If postgres patterns found in a query routed to sqlite → swap sub_query.db_type to "postgres".
Returns updated QueryPlan with corrected db_type.
```
