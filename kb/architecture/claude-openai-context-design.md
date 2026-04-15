# Claude Memory and OpenAI Data-Agent Context Design

## Purpose
This document captures the design bridge between:
- Claude-code style persistent memory discipline (structured, session-aware memory that can be corrected over time)
- OpenAI-style layered data-agent context design (separate mechanisms for schema, institutional knowledge, and runtime evidence)

The intent is operational: reduce hallucination, make tool use auditable, and keep context updates incremental rather than dumping one giant static prompt.

## Claude-Code Memory System Principles Applied Here
- Memory is separated into stable layers: index, topic summaries, session transcript.
- Session recency is prioritized over stale history.
- Corrections are persisted and re-read so known failures are less likely to repeat.
- Memory writes happen after execution outcomes, not before, so memory reflects observed behavior.

## OpenAI Data-Agent Context Design Principles Applied Here
- Context is assembled as explicit layers with precedence, not a single blob.
- Schema/tool metadata is injected before answer synthesis.
- Institutional and domain guidance are separate from runtime tool outputs.
- Runtime evidence from tool calls is privileged over prior assumptions.
- Low-confidence situations are surfaced explicitly instead of overconfident answers.

## Combined Design Decision in OracleForge
- Static guidance lives in `kb/architecture` and `kb/domain`.
- Dynamic guidance lives in session memory and corrections log.
- Runtime context includes discovered tools, selected db type, and mode flags.
- Final answers are grounded in tool evidence and surfaced with confidence.

## Injection Test Evidence
- Test query: "How does OracleForge combine persistent memory with layered context injection?"
- Expected answer: "It keeps persistent memory in structured files (index/topics/sessions), then injects a six-layer context packet where runtime evidence and current question take precedence over lower layers."
