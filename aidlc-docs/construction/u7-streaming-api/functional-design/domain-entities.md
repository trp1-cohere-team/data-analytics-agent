# U7 — Streaming API: Domain Entities

## StreamEvent
```
StreamEvent
  type        : Literal["thought", "action", "final_answer", "error"]
  iteration   : int | None          # present for thought / action
  action      : str | None          # thought: chosen_action name
  confidence  : float | None        # thought: LLM-reported confidence
  tool        : str | None          # action: MCP tool or sandbox name
  success     : bool | None         # action: did it succeed
  answer      : str | None          # final_answer: the answer text
  session_id  : str | None          # final_answer: session identifier
  iterations_used : int | None      # final_answer: total iterations run
  message     : str | None          # error: exception type name
```

## SSE Serialisation helper
```
format_sse(event: StreamEvent) -> str
  Returns: f"event: {event.type}\ndata: {event.model_dump_json(exclude_none=True)}\n\n"
```

## Orchestrator (modified — new method only)
```
Orchestrator
  +run(...)          -> OrchestratorResult          # UNCHANGED
  +run_stream(...)   -> AsyncGenerator[StreamEvent]  # NEW
```

## API Route (new)
```
POST /query/stream
  Request  : QueryRequest   (same as /query)
  Response : StreamingResponse(text/event-stream)
             — yields SSE-formatted StreamEvent strings
```
