# Domain Entities
# U1 — Agent Core & API

**Date**: 2026-04-11  
**Unit**: U1 — Agent Core & API  
**Answers applied**: Q1=B, Q2=C, Q3=A, Q4=B, Q5=B, Q6=A, Q7=B, Q8=A, Q9=C, Q10=B, Q11=B, Q12=B

---

## Entity Map

```
REQUEST PIPELINE
  QueryRequest          — inbound HTTP request body
  QueryResponse         — outbound HTTP response body
  HealthResponse        — GET /health response
  SchemaResponse        — GET /schema response

REACT LOOP
  ReactState            — mutable state threaded through one run() call
  Thought               — output of one think() step
  Observation           — output of one act() step
  TraceStep             — one iteration recorded for audit/return
  OrchestratorResult    — final output of Orchestrator.run()

CONTEXT LAYERS
  ContextBundle         — three-layer aggregate for one session
    SchemaContext       — Layer 1: all DB schemas (permanent cache)
    DomainContext       — Layer 2: KB documents (mtime-refreshed)
    CorrectionsContext  — Layer 3: recent corrections (per-session fresh load)

CORRECTION ENGINE
  CorrectionResult      — outcome of one CorrectionEngine.correct() call
  FailureType           — enum: SYNTAX_ERROR | JOIN_KEY_MISMATCH | WRONG_DB_TYPE | DATA_QUALITY | UNKNOWN
  JoinKeyMismatch       — details of a detected join key mismatch
```

---

## Entity Definitions

### QueryRequest
```
question: str           — natural language question (1–4096 chars)
databases: list[str] | None — optional list of db names to restrict routing
session_id: str | None  — caller-supplied session ID; used as-is if provided (Q11=B)
```

### QueryResponse
```
answer: Any             — final answer from Orchestrator (string, number, list, etc.)
query_trace: list[TraceStep]  — full ReAct trace (all iterations)
confidence: float       — LLM-reported confidence from final think() step (Q3=A)
session_id: str         — the session_id used for this request
```

### ReactState
```
query: str              — original natural language question
session_id: str         — UUID (caller-provided or server-generated)
iteration: int          — current loop counter (starts at 0)
history: list[TraceStep] — accumulated trace across all iterations
terminated: bool        — set to True when FINAL_ANSWER or max_iterations reached
final_answer: Any       — populated when terminated=True via FINAL_ANSWER
confidence: float       — last confidence value from think() (Q3=A: LLM-reported)
```

### Thought
```
reasoning: str          — LLM's chain-of-thought explanation
chosen_action: str      — one of: query_database | search_kb | extract_from_text | resolve_join_keys | FINAL_ANSWER
action_input: dict[str, Any]  — payload for the chosen action
confidence: float       — LLM-reported confidence score 0.0–1.0 (Q3=A)
```
Note: LLM returns a JSON object matching `{"reasoning": ..., "action": ..., "action_input": ..., "confidence": ...}` from the system prompt (Q1=B).

### Observation
```
action: str             — which action was executed
result: Any             — raw result from the tool (rows, docs, error description)
success: bool           — True if tool executed without error
error: str | None       — error description if success=False
```

### TraceStep
```
iteration: int          — which iteration this step belongs to
thought: str            — reasoning text from think()
action: str             — action name
action_input: dict      — action parameters
observation: str        — result/error description from act()
timestamp: float        — Unix epoch when step was completed
```

### OrchestratorResult
```
answer: Any             — final answer (from FINAL_ANSWER action_input or "could not answer" message)
query_trace: list[TraceStep]  — full history
confidence: float       — final LLM-reported confidence (0.0 if max_iterations hit without FINAL_ANSWER)
session_id: str
iterations_used: int
```
Note (Q2=C): when max_iterations is reached without FINAL_ANSWER, `answer` is a structured "I could not answer this question" string and `confidence` is 0.0.

### ContextBundle
```
schema_ctx: SchemaContext       — Layer 1 (permanent cache — loaded at startup)
domain_ctx: DomainContext       — Layer 2 (mtime-refreshed — background task Q6=A)
corrections_ctx: CorrectionsContext  — Layer 3 (per-session fresh load)
```

### DomainContext
```
documents: list[KBDocument]     — all non-CHANGELOG .md files from KB subdirs
loaded_at: datetime             — when this snapshot was loaded
```
Note: Layer 2 refresh checks file mtime of each `.md` file against `loaded_at` (Q6=A). If any file is newer, the entire domain context is reloaded.

### CorrectionsContext
```
corrections: list[CorrectionEntry]  — last N corrections (N = settings.corrections_limit)
session_memory: dict[str, Any]      — topics from MemoryManager.get_topics() for this session
```
Note: formatted for LLM as one Markdown bullet per entry: `- [FAILURE_TYPE] query_snippet → fix_strategy` (Q7=B).

### CorrectionResult
```
success: bool
corrected_query: str | None
corrected_plan: QueryPlan | None
fix_strategy: str               — rule_syntax | rule_join_key | rule_db_type | rule_null_guard | llm_corrector
attempt_number: int
error: str | None
```

### FailureType (enum)
```
SYNTAX_ERROR        — SQL syntax violation (missing quotes, wrong dialect keyword, GROUP BY error)
JOIN_KEY_MISMATCH   — cross-DB join key format incompatibility
WRONG_DB_TYPE       — query routed to wrong DB; detected from error signal patterns (Q10=B)
DATA_QUALITY        — null/missing field where non-null expected
UNKNOWN             — all cheaper strategies exhausted; LLM corrector required
```
