# DOMAIN_NOTES.md
# Oracle Forge — Domain Notes
# Weeks 8–9 · TRP1 FDE Program · April 2026

## Purpose

This document captures the domain-level knowledge the agent needs before answering business questions across heterogeneous databases. It exists because correct answers in DataAgentBench-style workloads depend not only on schema awareness, but also on institutional definitions, join-key normalization rules, unstructured-field handling, and execution heuristics. This is part of the Knowledge Base context layer described in the Oracle Forge challenge and facilitator manual.

---

## Critical Principle

Correct answers depend on:
1. correct data source selection
2. correct join-key normalization
3. correct domain definitions
4. correct handling of unstructured data

Failure in any of these leads to incorrect but plausible outputs.

---

## Core Problem Shape

The agent is expected to answer natural-language questions that may require:

1. Routing sub-questions across multiple database systems
2. Reconciling entity identifiers with inconsistent formatting
3. Extracting structured facts from unstructured text fields
4. Applying business/domain definitions not explicitly present in the schema
5. Producing a verifiable answer with query trace and auditability

The system must not assume:
- a single database
- clean schemas
- directly joinable identifiers
- purely structured fields
- that natural-language business terms map 1:1 to column names

---

## Database Environment Assumptions

The benchmark and challenge context assume work across these database types:

- PostgreSQL
- MongoDB
- SQLite
- DuckDB

### Operational implication
The agent must be able to:
- identify which source likely holds the needed information
- use the correct query dialect or tool pattern
- merge intermediate results safely
- recover when a query fails because of syntax, typing, schema mismatch, or join-key mismatch

---

## Domain Knowledge Categories

### 1. Schema Knowledge
What tables, collections, columns, and field types exist.

Examples:
- transactional facts
- customer/account entities
- support interactions
- product metadata
- event or log records

The agent should treat schema knowledge as necessary but insufficient.

---

### 2. Institutional / Semantic Knowledge
What business terms mean in this environment.

Examples:
- "active customer" may mean purchased in the last 90 days, not merely present in a table
- "revenue" may refer to net recognized revenue, not gross order value
- "repeat purchase rate" may require cohort logic rather than raw count comparison
- "support ticket volume" may require counting only valid/open/resolved CRM cases depending on the domain definition

This knowledge should live in the KB, not be inferred ad hoc when possible.

---

### 3. Join-Key Normalization Knowledge
How the same entity appears differently across systems.

Examples:
- integer customer IDs in PostgreSQL
- prefixed string IDs in MongoDB, e.g. `CUST-00123`
- mixed-case product codes
- zero-padded identifiers
- email vs internal ID as alternative entity references

The agent should:
- inspect examples before joining
- detect format mismatches explicitly
- normalize both sides before join or comparison
- record successful normalization patterns for reuse

---

### 4. Unstructured Field Knowledge
Which fields contain free text that must be transformed before use.

Examples:
- support notes
- review text
- product descriptions
- comments
- call transcripts
- issue summaries

The agent should not treat raw text as immediately countable or joinable. It must first extract:
- sentiment
- category
- entity
- event
- status
- reason
- time reference

This directly connects to the challenge requirement for unstructured text transformation.
---

## Default Reasoning Strategy

When the user asks a question, the agent should reason in this order:

1. Clarify the analytical target
   - What is being measured?
   - Over what time range?
   - At what grain? (customer, segment, product, month, quarter)

2. Identify required evidence sources
   - Which database likely contains each needed fact?

3. Identify reconciliation requirements
   - Are entities shared across sources?
   - Do IDs likely differ in format?

4. Check whether any business terms require KB lookup
   - e.g. churn, active, retained, repeat, valid ticket, premium user

5. Check whether any needed signals are trapped in unstructured fields

6. Execute sub-queries

7. Validate intermediate results
   - row counts
   - null rates
   - join cardinality
   - type assumptions
   - unexpected sparsity

8. Synthesize answer
   - include evidence
   - include assumptions
   - include traceability metadata

---

## Common Failure Modes

### Failure Mode A — Wrong Database Routing
The agent answers from a single source when the question actually spans multiple systems.

Mitigation:
- decompose the question into sub-facts
- map each sub-fact to candidate sources
- require explicit source justification before execution

### Failure Mode B — Naive Join on Mismatched Keys
The agent attempts a direct join across differently formatted IDs.

Mitigation:
- sample identifiers first
- compare type, prefix, casing, padding
- apply transformation before join

### Failure Mode C — Literal Interpretation of Business Terms
The agent maps a user term directly to a column name without semantic validation.

Mitigation:
- check KB for defined business terms
- fall back to documented assumptions when absent
- mark assumptions in trace

### Failure Mode D — No Transformation of Free Text
The agent tries to count or aggregate unstructured text without extracting structured meaning first.

Mitigation:
- identify text fields early
- run extraction/classification before aggregation
- preserve extraction rationale in trace

### Failure Mode E — Fluent but Unverifiable Output
The answer sounds plausible but lacks reproducible support.

Mitigation:
- require query trace
- preserve intermediate outputs
- attach confidence and validation notes

These failure modes align with the benchmark and manual emphasis on multi-database integration, ill-formatted join keys, unstructured text transformation, and domain knowledge requirements.

---

## Query Interpretation Heuristics

### Time-based questions
Map explicit or implicit windows carefully:
- Q3
- last 30 days
- month-over-month
- year-to-date
- trailing 90 days

Never assume fiscal periods equal calendar periods unless KB says so.

### Comparative questions
Examples:
- declining
- improved
- worse than before
- highest vs lowest
- correlated with

These require:
- baseline period
- comparison period
- metric definition
- aggregation grain

### Segment questions
Examples:
- customer segment
- plan tier
- region
- account type
- cohort

The segmentation rule must be sourced from schema or KB, not improvised.

### Correlation / relationship questions
Examples:
- correlate with
- associated with
- linked to
- tied to

The agent should distinguish:
- descriptive co-movement
- grouped comparison
- actual statistical correlation

Unless the workflow explicitly computes correlation, do not overstate the result.

---

## Output Contract

Every answer should aim to include:

- final answer
- key assumptions
- source systems used
- join or normalization rules applied
- unstructured extraction steps, if any
- validation notes
- query trace or reference to trace artifact

This is required because Oracle Forge is not just about answering correctly; it is about answering in an auditable way.

---

## Correction Logging Rule

Whenever the agent fails, log:

- original question
- failing step
- why it failed
- what fixed it
- whether the fix was schema, semantic, join-key, or extraction related

This becomes part of the KB corrections layer and should influence future runs.

---

## Practical Agent Policy

The agent should prefer:
- decomposition over monolithic generation
- inspected joins over assumed joins
- KB-backed definitions over guesswork
- explicit normalization over silent coercion
- auditable synthesis over elegant prose

The objective is not to look smart.
The objective is to be correct, recoverable, and inspectable.

---

## Minimal Checklist Before Returning an Answer

- Did I use all required source systems?
- Did I validate join-key compatibility?
- Did I check whether domain terms need KB interpretation?
- Did I transform text fields before aggregation?
- Did I validate intermediate outputs?
- Can another engineer reproduce this answer from my trace?

If any answer is “no”, do not finalize yet.
