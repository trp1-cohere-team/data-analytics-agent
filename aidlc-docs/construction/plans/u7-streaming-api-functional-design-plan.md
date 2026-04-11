# U7 — Streaming API: Functional Design Plan

**Unit**: U7 — Streaming API  
**Build Order**: 7th (after U6)  
**Purpose**: Stream agent progress to the caller so each Thought, tool call, and observation appears in real-time instead of waiting for the final answer.

---

## What Streaming does

Currently `POST /query` blocks until the full ReAct loop completes, then returns one JSON object. With streaming, the caller receives a sequence of events as they happen:

```
Client                           Agent
  |  POST /query/stream           |
  |-----------------------------> |
  |  event: thought               |
  | <----------------------------- |  iteration 1 — reasoning
  |  event: action                |
  | <----------------------------- |  iteration 1 — tool call
  |  event: observation           |
  | <----------------------------- |  iteration 1 — DB result
  |  event: thought               |
  | <----------------------------- |  iteration 2 — reasoning
  ...
  |  event: final_answer          |
  | <----------------------------- |  done
```

---

## Functional Design Questions

Please answer all questions using `[Answer]: <letter>` tags.

---

### Q1 — Streaming protocol
Which protocol should the streaming endpoint use?

A) **Server-Sent Events (SSE)** — HTTP/1.1 `text/event-stream`, works with `curl`, browsers, and most HTTP clients. Simple, one-direction.  
B) **WebSocket** — bidirectional, requires a WebSocket client. More complex, not needed here since flow is one-direction.  
C) **Chunked JSON lines (NDJSON)** — newline-delimited JSON over a regular streaming HTTP response. Works with any HTTP client, no special protocol.

[Answer]: A

---

### Q2 — Endpoint strategy
Should we add a new endpoint or modify the existing one?

A) **New endpoint** `POST /query/stream` — keeps `/query` unchanged; callers opt into streaming explicitly  
B) **Modify existing** `POST /query` — add `"stream": true` field to the request body to switch modes  
C) **Both** — keep `/query` as-is and add `/query/stream`

[Answer]: A

---

### Q3 — Event types to stream
Which events should be emitted to the client?

A) All events: `thought`, `action`, `observation`, `correction`, `final_answer`  
B) High-level only: `thought`, `action`, `final_answer` — omit raw DB observations (can be large)  
C) Minimal: `iteration_complete` (summary per iteration) + `final_answer`  
D) Just `final_answer` with a `delta` field — stream the answer text token by token

[Answer]: B

---

### Q4 — Event format
What should each streamed event look like?

A) `{"event": "thought", "iteration": 2, "data": {"action": "postgres_query", "confidence": 0.7}}`  
   — structured, metadata only, never logs reasoning text (consistent with SEC-U1-01)

B) `{"event": "thought", "iteration": 2, "reasoning": "I should look at orders table...", "action": "postgres_query"}`  
   — includes full reasoning text

C) `data: <json>\n\n` SSE format with `event:` line  
   — standard SSE envelope wrapping option A

[Answer]: C

---

### Q5 — Orchestrator changes
How should the Orchestrator emit streaming events?

A) **Async generator** — convert `Orchestrator.run()` to `async def run_stream()` that `yield`s events; the non-streaming `run()` stays unchanged  
B) **Callback injection** — add optional `on_event: Callable` parameter to existing `run()`; if provided, called at each step  
C) **asyncio.Queue** — orchestrator pushes to a queue; the API route drains it and streams to client

[Answer]: A

---

### Q6 — Error handling during stream
If the orchestrator raises an error mid-stream, what should happen?

A) Emit a final `{"event": "error", "message": "<ExceptionType>"}` event then close the stream — never expose stack traces  
B) Silently close the stream  
C) Emit error and attempt to continue

[Answer]: A

---

### Q7 — Backward compatibility
How important is it that existing tests and the non-streaming endpoint keep working exactly as before?

A) Critical — non-streaming `/query` must be 100% unchanged; add streaming as a purely additive new path  
B) Acceptable to refactor `/query` slightly if needed (e.g., shares internal logic with stream endpoint)

[Answer]: A
