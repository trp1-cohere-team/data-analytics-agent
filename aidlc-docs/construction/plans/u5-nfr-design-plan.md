# U5 NFR Design Plan
# Unit 5 — Utilities & Adversarial Probes

**Status**: All answers received — generation in progress  
**Date**: 2026-04-11

---

## Plan Checkboxes

- [x] Answer NFR design question (below)
- [x] Generate nfr-design-patterns.md — resilience pattern for SchemaIntrospector, PBT structure
- [x] Generate logical-components.md — timeout wrapper, PBT strategy registry
- [x] Update plan checkboxes, aidlc-state.md, audit.md
- [x] Present completion message

---

## NFR Design Category Assessment

| Category | Status | Rationale |
|---|---|---|
| Resilience Patterns | **APPLICABLE** | SchemaIntrospector partial-failure handling; JoinKeyUtils None-return guard |
| Scalability Patterns | N/A | Pure utility; no server; no concurrency design needed |
| Performance Patterns | N/A | No enforced budget; no caching or optimization patterns needed |
| Security Patterns | N/A | No user input, no secrets, no auth |
| Logical Components | **APPLICABLE** | Async timeout wrapper; PBT strategy registry |

---

## NFR Design Question

### Question 1: SchemaIntrospector — Per-DB Time Budget Within the 10s Total
The 10s total timeout is set. The 4 DB introspections run concurrently via `asyncio.gather`. How should the budget be managed per DB?

A) Shared budget — one `asyncio.timeout(10)` wraps the entire `asyncio.gather`. Whichever DBs complete within 10s are included. Slow DBs that haven't finished are cancelled. No per-DB sub-limit.
B) Equal per-DB sub-limits — each DB call gets `asyncio.timeout(2.5)` independently. A slow DB is cancelled at 2.5s; the other DBs still have their full 2.5s. Total max = 10s only if all DBs hit their limit.
C) Other (describe after [Answer]: tag)

[Answer]: C — outer hard ceiling of 9s (leaving 1s margin) wrapping the gather, plus per-DB sub-limits sized by DB type with a minimum floor, and completed results preserved on partial timeout

---

---

## Follow-up: Per-DB Sub-limits

Your answer specifies per-DB sub-limits "sized by DB type" but doesn't give the actual values. MongoDB samples 100 docs (slowest), PostgreSQL queries information_schema (moderate), SQLite/DuckDB use PRAGMA (fast). The outer ceiling is 9s.

What are the specific per-DB sub-limits and the minimum floor?

A) Tiered by expected speed:
   - MongoDB: 5s (document sampling is slowest)
   - PostgreSQL: 3s (information_schema joins can be slow on large DBs)
   - DuckDB: 2s
   - SQLite: 1s
   - Minimum floor: 1s (no DB gets less than 1s regardless)

B) Flat with MongoDB exception:
   - MongoDB: 5s
   - PostgreSQL, DuckDB, SQLite: 2s each
   - Minimum floor: 2s

C) Other — specify exact values after [Answer]: tag

[Answer]: C — values close to A but with the sum constrained below 9s and the floor set at 1s

---

Please fill in the [Answer]: tag above and let me know when done.
