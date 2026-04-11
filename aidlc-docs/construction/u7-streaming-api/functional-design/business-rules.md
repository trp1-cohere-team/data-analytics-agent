# U7 — Streaming API: Business Rules

## BR-U7-01: Existing /query endpoint is 100% unchanged
`POST /query` route, `Orchestrator.run()`, and all existing tests must not be modified. Streaming is purely additive.

## BR-U7-02: New endpoint is POST /query/stream
Route registered separately alongside existing routes in `create_app()`.

## BR-U7-03: SSE format — standard text/event-stream
Each event: `event: <type>\ndata: <json>\n\n`. Response Content-Type: `text/event-stream`. Cache-Control: `no-cache`.

## BR-U7-04: Event types emitted
Only `thought`, `action`, and `final_answer`. Observations (raw DB results) are NOT streamed — they can be large and contain data that should not transit the wire unnecessarily.

## BR-U7-05: Thought events carry metadata only (SEC-U1-01 extension)
`thought` events include: `iteration`, `action` (chosen action name), `confidence`. Never include reasoning text, query content, or observation content.

## BR-U7-06: Error mid-stream → error event + close
If `run_stream()` raises during iteration, emit `event: error\ndata: {"message": "ExceptionTypeName"}\n\n` then close the generator. No stack traces.

## BR-U7-07: Session save after stream completes
After the generator is exhausted (final_answer emitted), save the session transcript to MemoryManager best-effort, same as the non-streaming path.

## BR-U7-08: Rate limit applies to /query/stream
The same 20 req/min per-IP slowapi limiter applies to the streaming endpoint.

## BR-U7-09: run_stream() is a new method — run() is not modified
`Orchestrator.run_stream()` is added as a new `async def` that yields `StreamEvent` objects. `run()` is unchanged.
