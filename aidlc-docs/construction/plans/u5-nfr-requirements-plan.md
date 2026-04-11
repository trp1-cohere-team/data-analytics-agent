# U5 NFR Requirements Plan
# Unit 5 — Utilities & Adversarial Probes

**Status**: Awaiting user answers  
**Date**: 2026-04-11

---

## Plan Checkboxes

- [x] Answer NFR questions (below)
- [x] Generate nfr-requirements.md — performance, reliability, PBT requirements
- [x] Generate tech-stack-decisions.md — library choices and rationale
- [x] Update plan checkboxes, aidlc-state.md, audit.md
- [x] Present completion message

---

## NFR Category Assessment

| Category | Applicability | Rationale |
|---|---|---|
| Scalability | N/A | U5 is pure functions + file utilities; no server, no concurrency |
| Availability | N/A | No standalone process; U5 runs inside U1/U2 process |
| Security | N/A (minimal) | No user input, no secrets, no auth; MCP Toolbox is localhost only |
| Usability | N/A | No UI, no API — library code only |
| Performance | **APPLICABLE** | JoinKeyUtils is in the hot query path; called on every cross-DB query |
| Reliability | **APPLICABLE** | SchemaIntrospector must degrade gracefully; no MCP Toolbox dependency at runtime |
| Maintainability | **APPLICABLE** | Pure functions = high testability; PBT is a blocking extension |
| PBT (extension) | **BLOCKING** | Security Baseline + PBT both enabled; JoinKeyUtils is primary PBT target |

---

## NFR Questions

### Question 1: JoinKeyUtils Performance Budget
`detect_format` and `transform_key` are called synchronously inside `resolve_join_keys`, which runs before every cross-DB query execution. What's the acceptable latency per call?

A) < 1ms per call — pure in-memory computation; no I/O; must not add measurable overhead to query latency
B) < 10ms per call — acceptable for most use cases; occasional higher latency tolerated
C) No explicit budget — keep it fast but don't enforce a specific threshold
D) Other (describe after [Answer]: tag)

[Answer]: C

---

### Question 2: SchemaIntrospector Startup Timeout
`introspect_all()` is called once at server startup and blocks the server from becoming ready. If MCP Toolbox is slow or unavailable, how long should the agent wait before accepting partial/empty schema and starting anyway?

A) 10 seconds total across all 4 DBs — fail fast; if MCP Toolbox isn't ready in 10s, start with empty schema
B) 30 seconds total — allow MCP Toolbox more time to initialize (e.g. if it's starting concurrently)
C) 10 seconds per DB (40s max) — each DB gets its own timeout; one slow DB doesn't block others
D) Other (describe after [Answer]: tag)

[Answer]: A

---

### Question 3: Property-Based Testing Strategy for JoinKeyUtils
PBT is a blocking extension. JoinKeyUtils contains pure functions — ideal for Hypothesis. Which invariant properties must be tested?

A) Round-trip only — for every supported source→target format pair, `transform_key(transform_key(v, src, tgt), tgt, src)` must recover the original value (within precision).
B) Round-trip + output constraint — (A) plus: `detect_format([result])` must return `primary_format == target_fmt` for any transformed value (the output looks like what we said it would be).
C) Full invariant suite — (B) plus: idempotency (`transform_key` applied twice gives same result as once), monotonicity (`detect_format` on N samples gives same primary as on any majority-subset of those samples), expression validity (every non-None SQL expression from `build_transform_expression` is syntactically valid for its dialect).
D) Other (describe after [Answer]: tag)

[Answer]: C 

---

Please fill in the [Answer]: tags above and let me know when done.
