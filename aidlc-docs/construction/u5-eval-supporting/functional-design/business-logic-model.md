# Business Logic Model — U5 Eval + Supporting Files

## Overview
U5 provides the DAB evaluation harness, knowledge base seed content, project configuration,
adversarial probes, documentation, and the test suite (unit + PBT).
Minimal depth: all algorithms fully specified in FR-07, FR-09, FR-11, PBT-02/03.

---

## Module: eval/run_trials.py — Local Trial Runner (FR-07)

### Algorithm
```
1. Parse args: --trials N (default 2), --output path, --dataset list (default bookreview+stockmarket)
2. For each dataset in datasets:
   a. Load db_description from external/DataAgentBench/query_{dataset}/db_description.txt
   b. Load db_config from external/DataAgentBench/query_{dataset}/db_config.yaml
   c. List query dirs: external/DataAgentBench/query_{dataset}/query{N}/
   d. For each query:
      i. Load question from query.json
      ii. Extract db_hints from db_config (db_type fields)
      iii. For trial in range(trials):
           - Call run_agent(question, db_hints) → AgentResult
           - Compare answer against ground_truth.csv (exact match or partial)
           - Record {dataset, query_id, trial, question, answer, confidence, trace_id,
                     pass, ground_truth, duration_s}
3. Write results list to output JSON file (create results/ dir if needed)
4. Print summary: total queries, pass count, pass@1
```

### Pass@1 Definition
pass@1 = count(queries where at least 1 trial passed) / total queries

### Ground-truth comparison (simple heuristic)
Strip/lower both strings. Pass if ground_truth appears in agent answer or vice versa.

---

## Module: eval/run_dab_benchmark.py — Full DAB Benchmark (FR-07)

### Algorithm
```
1. Parse args: --trials N (default 5), --output path, --datasets list (default ALL 12)
2. For each dataset:
   a. Enumerate all query dirs
   b. For each query x trials: call run_agent, record result
3. Write results to output JSON
4. Print per-dataset and overall pass@1
```

---

## Module: eval/score_results.py — Scorer (FR-07)

### Algorithm
```
1. Parse args: --results path
2. Load results JSON list
3. Compute per-query pass@1: passed[q] = any(t['pass'] for t in query_trials)
4. Overall pass@1 = sum(passed.values()) / len(passed) (or 0.0 if empty)
5. Write dab_detailed.json: per-query breakdown
6. Write dab_submission.json: {pass_at_1: float, dataset_scores: {}}
7. Print overall pass@1
```

### Invariants (PBT-03)
- pass@1 is always in [0.0, 1.0]

---

## tests/test_properties.py — Hypothesis PBT (PBT-02/03)

### PBT-02: Round-trip tests
- `ContextPacket.to_dict()` → `from_dict()` round-trip
- `TraceEvent.to_dict()` → `from_dict()` round-trip

### PBT-03: Invariant tests
- `failure_diagnostics.classify()` always returns one of 4 valid categories
- Layer 6 (user_question) always present in assembled prompt
- `score_results` pass@1 always in [0.0, 1.0]

---

## Security Compliance Summary
| Rule | Status | Rationale |
|---|---|---|
| SECURITY-03 | Compliant | All eval scripts use logging |
| SECURITY-05 | N/A | No external API parameters in eval scripts |
| SECURITY-10 | Compliant | requirements.txt pinned exact versions |
| SECURITY-15 | Compliant | Eval scripts catch exceptions; never crash |

## PBT Compliance Summary
| Rule | Status | Rationale |
|---|---|---|
| PBT-02 | Compliant | Round-trip tests for ContextPacket + TraceEvent |
| PBT-03 | Compliant | Invariant tests for classify() + pass@1 range |
| PBT-07 | Compliant | Domain-specific st.builds() generators used |
| PBT-08 | Compliant | Hypothesis default shrinking enabled |
| PBT-09 | Compliant | hypothesis in requirements.txt |
