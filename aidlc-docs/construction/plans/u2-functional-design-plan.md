# U2 Functional Design Plan
# Unit 2 — Multi-DB Execution Engine

**Status**: Complete  
**Date**: 2026-04-11

---

## Unit Context

| Item | Detail |
|---|---|
| Unit | U2 — Multi-DB Execution Engine |
| Build order | 2nd (after U5) |
| Files | `agent/execution/engine.py`, `agent/execution/mcp_client.py` |
| Requirements covered | FR-02 (all 4 DB types), FR-05 (join key resolution), FR-11 (MCP Toolbox) |
| Imports from U5 | `JoinKeyUtils.detect_format`, `JoinKeyUtils.build_transform_expression`, `JoinKeyUtils.transform_key` |

---

## Functional Design Steps

- [x] Q1 answered: MergeSpec operations (D — UNION + LEFT_JOIN + FIRST_ONLY)
- [x] Q2 answered: Partial failure behavior (B — partial results + failure info)
- [x] Q3 answered: JoinKeyResolver timing (C — pre-exec SQL + post-result MongoDB)
- [x] Q4 answered: MongoDB query format (A — pre-built pipeline, pass through)
- [x] Generate business-logic-model.md
- [x] Generate business-rules.md
- [x] Generate domain-entities.md

---

## Questions

### Q1 — Result Merge Operations

The `ResultMerger` must combine results from multiple sub-queries per a `MergeSpec`. Which merge strategies does it need to support?

**A** — UNION only (stack rows from all sub-queries; used when each DB returns independent rows)  
**B** — UNION + FIRST_ONLY (UNION for parallel reads; FIRST_ONLY returns result from whichever sub-query succeeds first — useful for fallback patterns)  
**C** — UNION + INNER_JOIN by key + FIRST_ONLY (full set: stack, join-by-key, or take-first)  
**D** — UNION + LEFT_JOIN by key + FIRST_ONLY (same as C but LEFT_JOIN instead of INNER_JOIN, preserving unmatched rows from the left result)

[Answer Q1]: D — UNION + LEFT_JOIN by key + FIRST_ONLY

---

### Q2 — Partial Failure Behavior

A QueryPlan may have 2+ sub-queries. If one sub-query fails (DB error / timeout), how should the engine behave?

**A** — Fail the entire plan immediately: wrap in `ExecutionFailure` and return to caller; no partial results  
**B** — Continue with remaining sub-queries; return partial results alongside an `ExecutionFailure` describing which sub-queries failed  
**C** — Continue with remaining sub-queries; return partial results only if the MergeSpec strategy is UNION; fail immediately for JOIN strategies (joining against an empty result is meaningless)  
**D** — Retry failed sub-query once (same 30s timeout); if still failing, fall through to B

[Answer Q2]: B

---

### Q3 — JoinKeyResolver Timing

When does join key resolution happen in the execution flow?

**A** — Pre-execution: JoinKeyResolver inspects the QueryPlan's cross-DB sub-queries, detects key format mismatches using `detect_format`, and rewrites the sub-query SQL expressions (via `build_transform_expression`) before any DB call is made  
**B** — Post-result: Sub-queries execute as-is, then JoinKeyResolver inspects the returned result rows, detects mismatches from the data, and transforms the join key column values (via `transform_key`) in-memory before merging  
**C** — Both: Pre-execution rewrites SQL expressions for structured DBs (PostgreSQL, SQLite, DuckDB); post-result row-level transform for MongoDB (which returns documents, not tabular SQL)

[Answer Q3]: C

---

### Q4 — MongoDB Query Format

The MCP Toolbox `mongodb_aggregate` tool takes a `pipeline` (a list of aggregation stage objects). What format does MultiDBEngine receive for MongoDB sub-queries from the Orchestrator?

**A** — Pre-built pipeline: the Orchestrator/LLM generates the complete MongoDB aggregation pipeline list; MultiDBEngine passes it through unchanged to MCP Toolbox  
**B** — SQL-like string: MultiDBEngine receives a SQL-like query string and must translate it into a MongoDB pipeline (basic SELECT/WHERE/LIMIT → $match/$project/$limit translation)  
**C** — Structured query dict: MultiDBEngine receives a structured dict with keys like `collection`, `filter`, `project`, `sort`, `limit`; it assembles the pipeline from these components

[Answer Q4]: A

---
