# Unit Test Execution Instructions — The Oracle Forge

**Date**: 2026-04-11

---

## Overview

Unit tests are fully isolated — they require no running services (no MCP Toolbox, no agent server, no databases). All external calls are mocked.

---

## Run All Unit Tests

```bash
pytest tests/unit/ -v
```

**Expected**: All tests pass. 0 failures. 0 errors.

---

## Run Tests by Unit

```bash
# U5 — Utilities & Adversarial Probes
pytest tests/unit/test_join_key_utils.py tests/unit/test_multi_pass_retriever.py \
       tests/unit/test_schema_introspector.py tests/unit/test_probe_runner.py -v

# U2 — Multi-DB Execution Engine
pytest tests/unit/test_engine.py tests/unit/test_mcp_client.py -v

# U3 — Knowledge Base & Memory
pytest tests/unit/test_knowledge_base.py tests/unit/test_memory_manager.py -v

# U1 — Agent Core & API
pytest tests/unit/test_api.py tests/unit/test_orchestrator.py \
       tests/unit/test_context_manager.py tests/unit/test_correction_engine.py -v

# U4 — Evaluation Harness
pytest tests/unit/test_harness.py tests/unit/test_scorers.py -v
```

---

## Run Property-Based Tests (PBT)

PBT tests run alongside regular unit tests. To run them explicitly:

```bash
pytest tests/unit/ -v -k "PBT or invariant or self_consistency or round_trip"
```

### PBT Inventory

| ID | File | Property | Examples |
|---|---|---|---|
| PBT-U5-01 | `test_join_key_utils.py` | Format detection majority vote | 200 |
| PBT-U5-02 | `test_join_key_utils.py` | Transform expression structural validity | 200 |
| PBT-U5-03 | `test_multi_pass_retriever.py` | Retrieval pass ordering | 100 |
| PBT-U5-04 | `test_multi_pass_retriever.py` | Top-N bounded | 100 |
| PBT-U5-05 | `test_join_key_utils.py` | SQL expression dialect validity | 150 |
| PBT-U3-01 | `test_knowledge_base.py` | CorrectionEntry JSON round-trip | 200 |
| PBT-U3-02 | `test_knowledge_base.py` | N appends = N corrections count | 100 |
| PBT-U3-03 | `test_knowledge_base.py` | Token gate boundary | 150 |
| PBT-U3-04 | `test_memory_manager.py` | save_session uniqueness | 100 |
| PBT-U3-05 | `test_memory_manager.py` | Merge idempotency | 150 |
| PBT-U3-06 | `test_memory_manager.py` | SessionMemory round-trip | 200 |
| PBT-U1-01 | `test_correction_engine.py` | classify_failure returns valid FailureType | 300 |
| PBT-U1-02 | `test_orchestrator.py` | fix_syntax_error output len >= input len | 200 |
| PBT-U4-01 | `test_scorers.py` | ExactMatch self-consistency | 500 |
| PBT-U4-02 | `test_harness.py` | ScoreLog append/load round-trip | 200 |

---

## Run With Coverage Report

```bash
pytest tests/unit/ --cov=agent --cov=eval --cov=utils --cov=probes \
       --cov-report=term-missing --cov-report=html:coverage_html/
```

Coverage report at `coverage_html/index.html`.

---

## Run Adversarial Probe Unit Tests

```bash
pytest tests/unit/test_probe_runner.py -v
```

Note: `test_probe_runner.py` tests the ProbeRunner parsing and scoring logic with mocked HTTP — no live agent required.

---

## Expected Test Counts

| Unit | Test File(s) | Approx Tests |
|---|---|---|
| U5 | test_join_key_utils, test_multi_pass_retriever, test_schema_introspector, test_probe_runner | ~65 |
| U2 | test_engine, test_mcp_client | ~40 |
| U3 | test_knowledge_base, test_memory_manager | ~55 |
| U1 | test_api, test_orchestrator, test_context_manager, test_correction_engine | ~60 |
| U4 | test_harness, test_scorers | ~35 |
| **Total** | | **~255** |

---

## Fixing Failing Tests

1. Run `pytest tests/unit/ -v --tb=short` to see full traceback
2. Check if failure is in application code or test setup (mock wiring)
3. For PBT failures: Hypothesis prints the minimal counterexample — examine it carefully
4. Fix the underlying code; do not modify test invariants to hide failures
