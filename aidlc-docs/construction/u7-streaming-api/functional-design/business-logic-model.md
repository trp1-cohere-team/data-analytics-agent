# U7 — Streaming API: Business Logic Model

## Streaming Flow

```
Client                              Agent API                        Orchestrator
  │                                     │                                │
  │  POST /query/stream                 │                                │
  │  {"question": "...",                │                                │
  │   "session_id": "..."}              │                                │
  │ ─────────────────────────────────>  │                                │
  │                                     │  run_stream(query, ctx, ...)   │
  │  HTTP 200 text/event-stream         │ ─────────────────────────────> │
  │ <─────────────────────────────────  │                                │ (iteration 1)
  │                                     │  yield StreamEvent(thought)    │
  │  event: thought                     │ <─────────────────────────────  │
  │  data: {"action":"...", ...}        │                                │
  │ <─────────────────────────────────  │                                │
  │                                     │  yield StreamEvent(action)     │
  │  event: action                      │ <─────────────────────────────  │
  │  data: {"tool":"...", ...}          │                                │
  │ <─────────────────────────────────  │                                │
  │                                     │         (iterations N…)        │
  │                                     │  yield StreamEvent(final)      │
  │  event: final_answer                │ <─────────────────────────────  │
  │  data: {"answer":"...", ...}        │                                │
  │ <─────────────────────────────────  │                                │
  │  [connection closed]                │                                │
```

## SSE Wire Format

Each event is formatted as standard Server-Sent Events:

```
event: thought
data: {"iteration": 1, "action": "postgres_query", "confidence": 0.72}

event: action
data: {"iteration": 1, "tool": "postgres_query", "success": true}

event: final_answer
data: {"answer": "Revenue was $42,000.", "confidence": 0.91, "session_id": "abc-123", "iterations_used": 2}

```

*(Two newlines terminate each event block)*

## Orchestrator run_stream() Generator

New method alongside the existing `run()` (which is NOT modified):

```
async def run_stream(query, session_id, context, max_iterations, confidence_threshold)
  → AsyncGenerator[StreamEvent, None]

  Per iteration:
    1. think()  →  yield StreamEvent(type="thought", iteration=N, action=chosen_action, confidence=X)
    2. act()    →  yield StreamEvent(type="action",  iteration=N, tool=tool_name, success=bool)
    3. if FINAL_ANSWER → yield StreamEvent(type="final_answer", ...) → return

  On exception:
    yield StreamEvent(type="error", message=type(exc).__name__) → return
```

## API Route

```
POST /query/stream
  Content-Type: application/json
  Body: QueryRequest (same model as /query)

  Response:
    Status: 200
    Content-Type: text/event-stream
    Cache-Control: no-cache
    Body: SSE event stream (see wire format above)
```

Implemented with FastAPI `StreamingResponse`.
