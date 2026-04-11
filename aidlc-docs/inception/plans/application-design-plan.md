# Application Design Plan
# The Oracle Forge — Data Analytics Agent

**Status**: Awaiting user answers  
**Date**: 2026-04-11

---

## Design Plan Checkboxes

- [x] Answer design questions (below)
- [x] Generate components.md — 5 component definitions and responsibilities
- [x] Generate component-methods.md — method signatures per component
- [x] Generate services.md — orchestration service layer
- [x] Generate component-dependency.md — dependency matrix and data flow
- [x] Generate application-design.md — consolidated design document
- [x] Validate design completeness and consistency

---

## Context Summary

From requirements analysis, the system has **5 major components**:
1. **Agent Core & API** — FastAPI server, LLM interface, context loading pipeline
2. **Multi-DB Execution Engine** — Query router + 4 DB connectors + join key resolver
3. **Knowledge Base & Memory System** — KB loader, JSON memory (MEMORY.md pattern), corrections log
4. **Evaluation Harness** — Benchmark runner, scorer, query tracer, regression suite
5. **Utilities** — Shared modules (retrieval helper, schema introspection, join key resolver)

The challenge documents specify: MCP Toolbox for DB connections, AGENT.md context file, FastAPI server, OpenRouter/GPT-4o as LLM.

The following design questions address the genuinely ambiguous architecture boundaries. Please answer each one.

---

## Design Questions

### Question 1
How should the FastAPI agent server and MCP Toolbox binary relate at deployment?

A) Two separate processes — FastAPI calls MCP Toolbox via HTTP on localhost:5000 (recommended: clean separation, MCP Toolbox is an independent binary)
B) MCP Toolbox embedded as a subprocess — FastAPI spawns and manages the toolbox process lifecycle
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 2
How should the three context layers be loaded when the agent receives a query?

A) Eager loading at server startup — all layers pre-loaded into memory before first query (faster queries, higher memory use)
B) Lazy loading per session — layers loaded when a session starts, cached for session duration
C) Hybrid — Layer 1 (schema) at startup, Layers 2+3 (KB, memory) loaded per-query from files
D) Other (please describe after [Answer]: tag below)

[Answer]: D — a three-way split matching each layer's actual change frequency
Layer 1 (schema)      → load once at server startup, cache in memory permanently
Layer 2 (domain KB)   → load once per server process, reload only on file change
Layer 3 (corrections) → load once per session start, never cache across sessions

---

### Question 3
What architectural pattern should govern the agent's internal structure?

A) Layered (n-tier) — clear separation: API layer → service layer → execution layer → data layer
B) Pipeline — each query flows through a fixed sequence of stages (context load → plan → execute → validate → respond)
C) Other (please describe after [Answer]: tag below)

[Answer]: C — ReAct loop as the control flow pattern, with layered architecture as the packaging structure
These two ideas operate at different levels and should both be present:

Layered architecture governs how your code is organized — API layer, orchestrator layer, execution layer, data layer. Use this. It keeps the codebase navigable.
ReAct loop governs how control flows inside the orchestrator — think, act, observe, repeat until done or until confidence threshold is met.
---

### Question 4
How should the self-correction loop be implemented?

A) Retry loop in the execution engine — on failure, diagnose error type and retry with modified query (max 3 attempts, same LLM call structure)
B) Separate corrector agent — a second LLM call receives the error + original query and produces a corrected query
C) Other (please describe after [Answer]: tag below)

[Answer]: C — Tiered correction: classify the failure first, then apply the cheapest sufficient fix for that failure typeNot a retry loop. Not a blanket corrector agent. A classifier that routes each failure to the right correction strategy — three of which don't need an LLM at all.

---

Please fill in the [Answer]: tags above, then let me know when done.
