# Business Logic Model — U3 Runtime Layer

## Overview
U3 is the orchestration spine: persistent memory for cross-session knowledge, tool policy enforcement as a security barrier, and the conductor that ties everything together — context assembly, LLM calls, tool invocation, and the self-correction loop.

---

## Module: memory.py — 3-Layer Persistent Memory (FR-05)

### Responsibilities
- Manage 3-layer file-based memory under `AGENT_MEMORY_ROOT`
- Layer 1: `index.json` — topic → file mapping
- Layer 2: `topics/<key>.md` — condensed topic knowledge (max `AGENT_MEMORY_TOPIC_CHARS`)
- Layer 3: `sessions/<session_id>.jsonl` — turn-by-turn transcript (max `AGENT_MEMORY_SESSION_ITEMS`)
- Lazy initialization — zero side effects on import, first write creates structure

### Public API

**`MemoryManager`** class:
- `__init__(self, root: str, session_id: str)` — stores paths; does NOT create files
- `load_session(self) -> list[MemoryTurn]` — read session transcript
- `save_turn(self, turn: MemoryTurn) -> None` — append turn, enforce cap
- `load_topic(self, key: str) -> str` — read topic content
- `save_topic(self, key: str, content: str) -> None` — write topic, enforce char cap
- `get_index(self) -> dict[str, str]` — return topic index
- `get_memory_context(self) -> str` — assemble memory for context Layer 5

### Algorithm: save_turn
```
1. Ensure sessions/ directory exists (lazy create)
2. Read existing turns from sessions/{session_id}.jsonl
3. Append new turn
4. If len(turns) > AGENT_MEMORY_SESSION_ITEMS:
   a. Trim oldest turns to fit cap
5. Write all turns back to file (overwrite — bounded file)
```

### Algorithm: save_topic
```
1. Ensure topics/ directory exists (lazy create)
2. Truncate content to AGENT_MEMORY_TOPIC_CHARS
3. Write to topics/{key}.md
4. Update index.json with key → filename mapping
```

### Algorithm: get_memory_context
```
1. Load session turns → format as conversation excerpt
2. Load all topics from index → concatenate summaries
3. Return combined string for Layer 5 (interaction_memory)
```

### Error Handling
- All file operations wrapped in try/except (SEC-15)
- Missing files → return defaults (empty list, empty string)
- Corrupted JSONL → skip malformed lines, log warning (SEC-13)

---

## Module: tooling.py — ToolRegistry + ToolPolicy (FR-03, SEC-05, SEC-11)

### Responsibilities
- `ToolRegistry`: db_type hint → tool selection from MCPClient's 4-tool list
- `ToolPolicy`: mutation guard, payload size cap — security barrier before tool invocation

### Public API

**`ToolRegistry`** class:
- `__init__(self, mcp_client: MCPClient)` — discovers tools at init
- `get_tools(self) -> list[ToolDescriptor]` — return all tools
- `select_tool(self, db_hints: list[str]) -> ToolDescriptor | None` — select best tool for given DB hints
- `get_tool_by_name(self, name: str) -> ToolDescriptor | None` — lookup by name

**`ToolPolicy`** class (security-critical — SEC-11):
- `validate_invocation(self, tool_name: str, params: dict) -> tuple[bool, str]` — returns (ok, error_msg)

### Algorithm: select_tool
```
1. Get all tools from MCPClient.discover_tools()
2. For each db_hint in db_hints:
   a. Map hint to db_type (e.g., "postgresql" → "postgres", "duckdb" → "duckdb")
   b. Find tool whose db_type_from_kind(tool.kind) matches
   c. Return first match
3. If no match found, return first tool as fallback (or None if empty)
```

### Algorithm: ToolPolicy.validate_invocation
```
1. Check tool_name is non-empty string
2. Check params is dict
3. If params contains "sql" key:
   a. Check SQL length <= SANDBOX_MAX_PAYLOAD_CHARS
   b. Check SQL does NOT contain mutation keywords:
      INSERT, UPDATE, DELETE, DROP, CREATE, ALTER (case-insensitive, word boundary)
   c. If mutation detected: return (False, "mutation_blocked: {keyword}")
4. Return (True, "")
```

### Mutation Keywords (SEC-05)
Blocked: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`
Match rule: case-insensitive, word-boundary match (avoid false positives like "CREATED_AT")

---

## Module: conductor.py — Orchestration Spine (FR-01, FR-04, FR-06)

### Responsibilities
- Session lifecycle management
- 6-layer context assembly (delegating to U2 modules)
- LLM call orchestration (OpenRouter API)
- Tool invocation via MCPClient (through ToolRegistry + ToolPolicy)
- Self-correction loop (max `AGENT_SELF_CORRECTION_RETRIES`)
- Event emission for every step
- Global error handler returning safe AgentResult (SEC-15)

### Public API

**`OracleForgeConductor`** class:
- `__init__(self, session_id: str | None = None)` — init all subsystems
- `run(self, question: str, db_hints: list[str]) -> AgentResult` — main orchestration

### Algorithm: __init__
```
1. Set session_id (from param or config or generate UUID)
2. Create MCPClient()
3. Create ToolRegistry(mcp_client)
4. Create ToolPolicy()
5. Create MemoryManager(AGENT_MEMORY_ROOT, session_id)
6. Emit session_start event
```

### Algorithm: run (main orchestration loop)
```
1. Validate inputs: question (str, max 4096 chars), db_hints (list[str], max 10) — SEC-05
2. Load AGENT.md into Layer 3 (institutional_knowledge) — FR-08
3. Load KB context for query → Layers 2+3
4. Load memory context → Layer 5
5. Build runtime_context dict → Layer 4 (session_id, discovered_tools, selected_dbs)
6. Assemble ContextPacket with all 6 layers
7. Assemble prompt via assemble_prompt()

8. Enter execution loop (max AGENT_MAX_EXECUTION_STEPS):
   a. Call LLM with assembled prompt → get execution plan / tool call
   b. If LLM returns final answer: break to synthesis
   c. Extract tool call from LLM response
   d. ToolPolicy.validate_invocation() → if blocked, add error to context, continue
   e. Invoke tool via MCPClient.invoke_tool()
   f. Emit tool_call + tool_result events
   g. If success: add result to context, continue loop
   h. If failure: enter self-correction sub-loop

9. Self-correction sub-loop (max AGENT_SELF_CORRECTION_RETRIES):
   a. Classify failure via failure_diagnostics.classify()
   b. Emit correction event with retry_count
   c. Write CorrectionEntry to corrections log
   d. Rebuild prompt with diagnosis + correction suggestion
   e. Re-call LLM for corrected plan
   f. Re-invoke tool
   g. If success: break back to main loop
   h. If still failing: increment retry, loop

10. Synthesize final answer from execution evidence
11. Save session turn to memory
12. Emit session_end event
13. Return AgentResult(answer, confidence, trace_id, tool_calls, failure_count)
```

### Algorithm: _call_llm (private)
```
1. If AGENT_OFFLINE_MODE: return OFFLINE_LLM_RESPONSE (from config.py)
2. POST to OPENROUTER_BASE_URL/chat/completions with:
   - model: OPENROUTER_MODEL
   - messages: [system prompt + context, user question]
   - max_tokens: AGENT_MAX_TOKENS
   - temperature: AGENT_TEMPERATURE
   - headers: {"HTTP-Referer": OPENROUTER_APP_NAME}
3. Timeout: AGENT_TIMEOUT_SECONDS
4. Parse response → extract assistant message
5. On error: return safe fallback, log warning
```

### Global Error Handler (SEC-15)
```
try:
    return self._run_inner(question, db_hints)
except Exception as exc:
    logger.error("Conductor unhandled error: %s", exc)
    emit_event(error event)
    return AgentResult(
        answer="An internal error occurred. Please try again.",
        confidence=0.0,
        trace_id=self._trace_id,
        failure_count=999
    )
```
