# U1 Functional Design Plan
# Unit 1 — Agent Core & API

**Status**: In Progress  
**Date**: 2026-04-11

---

## Unit Context

**Components**: AgentAPI (`agent/api/app.py`), Orchestrator (`agent/orchestrator/react_loop.py`), ContextManager (`agent/context/manager.py`), CorrectionEngine (`agent/correction/engine.py`)  
**Depends on**: U5 (SchemaIntrospector, MultiPassRetriever), U2 (MultiDBEngine), U3 (KnowledgeBase, MemoryManager)  
**Artifacts to produce**:
- `aidlc-docs/construction/u1-agent-core-api/functional-design/domain-entities.md`
- `aidlc-docs/construction/u1-agent-core-api/functional-design/business-logic-model.md`
- `aidlc-docs/construction/u1-agent-core-api/functional-design/business-rules.md`

---

## Functional Design Questions

### Orchestrator — ReAct Loop

**Q1** — How does the Orchestrator instruct the LLM which tools are available?

A) Tool definitions passed in `tools=[]` parameter (OpenAI function-calling format); LLM returns a `tool_call` object  
B) Tools described in the system prompt as a plain text list; LLM returns a JSON blob with `action` and `action_input` fields  
C) Tools described in system prompt; LLM returns free-form text that is then parsed with regex  
D) Mix: function-calling for `query_database`; text parsing for the others  

[Answer]: B

---

**Q2** — When max_iterations is reached without a `FINAL_ANSWER`, what does the Orchestrator return?

A) Raise a `MaxIterationsExceeded` exception that the API catches and returns as HTTP 500  
B) Return whatever the last observation was as the answer with confidence = 0.0  
C) Return a structured "I could not answer this question" response with confidence = 0.0 and the full trace  
D) Retry from iteration 1 using a simplified prompt  

[Answer]: C

---

**Q3** — How is confidence scored in `think()`?

A) LLM outputs a numeric confidence score 0.0–1.0 as part of its structured response  
B) Heuristic: starts at 0.0, increments +0.1 per successful observation, capped at 1.0  
C) Only set to 1.0 on `FINAL_ANSWER` action; 0.0 for all other actions  
D) Set based on how many sub-queries succeeded vs failed (success_ratio)  

[Answer]: A

---

**Q4** — What does the `query_database` action input look like when the LLM produces it?

A) Raw SQL string only — Orchestrator wraps it in a `QueryPlan` before calling `MultiDBEngine`  
B) Full `QueryPlan` JSON (sub_queries, merge_spec) — LLM generates the entire plan  
C) Natural language description — Orchestrator uses another LLM call to convert to a `QueryPlan`  
D) DB name + SQL pairs list — Orchestrator builds the `QueryPlan` from them  

[Answer]: B

---

**Q5** — What happens when a `query_database` action fails and correction is attempted?

A) Orchestrator calls `CorrectionEngine.correct()`, which returns a corrected plan; Orchestrator re-executes immediately  
B) Orchestrator calls `CorrectionEngine.correct()`, records correction to KB, then loops back to `think()` with the error observation  
C) Orchestrator retries the same plan up to 3 times before calling CorrectionEngine  
D) CorrectionEngine is called automatically inside MultiDBEngine — Orchestrator never knows correction happened  

[Answer]: B

---

### ContextManager — Layer Assembly

**Q6** — For Layer 2 (domain KB), how does the background refresh task detect changes?

A) File modification time (mtime) comparison against a stored snapshot  
B) SHA-256 hash of each file compared against a stored hash  
C) Directory entry count comparison (new files added = reload)  
D) Fixed TTL of `layer2_refresh_interval_s` — always reloads unconditionally  

[Answer]: A

---

**Q7** — How is the Layer 3 corrections context formatted for injection into the LLM prompt?

A) Raw JSON array of the last N `CorrectionEntry` records  
B) Markdown summary: one bullet per entry with failure_type, original_query snippet, and fix_strategy  
C) Only entries where `success=True` are included; formatted as `(failure_type) → (corrected_query)`  
D) Passed as a separate tool-response message in the conversation history  

[Answer]: B

---

**Q8** — Where/when does `MemoryManager.save_session()` get called?

A) AgentAPI calls it after receiving the `OrchestratorResult`, before returning HTTP response  
B) Orchestrator calls it at the end of `run()` before returning `OrchestratorResult`  
C) A background task in ContextManager saves it asynchronously after each session  
D) It is not called in U1 — saved by a separate post-processing hook  

[Answer]: A

---

### CorrectionEngine — Fix Strategies

**Q9** — What specific patterns does `fix_syntax_error` handle (rule-based only)?

A) Missing semicolons, unquoted string literals, wrong aggregate name (eg. `COUNT(*)` vs `count`)  
B) Missing WHERE clause, wrong JOIN type, mismatched column aliases  
C) Missing quotes around string values, `GROUP BY` without aggregate, wrong dialect keyword (eg. `LIMIT` vs `ROWNUM`)  
D) All of A and C — a combined set of both dialect and structural fixes  

[Answer]: C

---

**Q10** — When `fix_wrong_db_type` is called, how does it detect which DB was the wrong choice?

A) Parses DB-specific error keywords from the error message (eg. "syntax error near" for SQLite, "psycopg2" for Postgres)  
B) Checks db_type in ExecutionFailure against known error signal patterns per db_type  
C) Uses the same `_classify_error` function from U2's mcp_client to re-classify; swaps db_type to next in priority order  
D) Asks the LLM to identify the correct db_type from the error  

[Answer]: B

---

### AgentAPI — Sessions and Security

**Q11** — When a caller provides a `session_id` in the `QueryRequest`, what happens?

A) Rejected — session_id is always generated server-side  
B) Accepted and used as-is — allows client-side session continuity  
C) Accepted only if it matches an existing saved session; otherwise rejected with 400  
D) Ignored — a new session_id is always generated regardless  

[Answer]: B

---

**Q12** — What security headers does the middleware add?

A) `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` only  
B) `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'none'`  
C) Full OWASP header set: above plus `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`  
D) None at the middleware level — headers added per-route handler  

[Answer]: B

---

## Plan Steps

- [x] **Step 1** — Log answers and validate (no ambiguities)
- [x] **Step 2** — Generate `domain-entities.md` (ReactState, Thought, Observation, OrchestratorResult, ContextBundle layers, CorrectionResult)
- [x] **Step 3** — Generate `business-logic-model.md` (ReAct loop flow, ContextManager assembly, CorrectionEngine tiers, AgentAPI request pipeline)
- [x] **Step 4** — Generate `business-rules.md` (iteration limits, confidence threshold, correction attempt limits, session_id handling, token budget for context, error response policy)
- [x] **Step 5** — Update aidlc-state.md and audit.md; present completion message
