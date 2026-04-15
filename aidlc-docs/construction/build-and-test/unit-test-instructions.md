# Unit Test Execution — OracleForge Data Agent

## Run All Unit Tests

### 1. Execute Full Test Suite (offline mode)
```bash
AGENT_OFFLINE_MODE=1 python3 -m unittest discover -s tests -v
```

### 2. Run Individual Test Files
```bash
# Conductor (U3) — offline pipeline + input validation
AGENT_OFFLINE_MODE=1 python3 -m unittest tests/test_conductor.py -v

# Context Layering (U2) — 6-layer assembly + prompt format
AGENT_OFFLINE_MODE=1 python3 -m unittest tests/test_context_layering.py -v

# Failure Diagnostics (U2) — 4-category classifier + DuckDB mapping
AGENT_OFFLINE_MODE=1 python3 -m unittest tests/test_failure_diagnostics.py -v

# Memory Manager (U3) — lazy init + session cap
AGENT_OFFLINE_MODE=1 python3 -m unittest tests/test_memory.py -v

# Property-based tests (U5/PBT) — round-trip + invariants
AGENT_OFFLINE_MODE=1 python3 -m unittest tests/test_properties.py -v
```

### 3. Expected Results
- **Total**: 39 tests
- **Pass**: 39
- **Fail**: 0
- **Status**: All green

### 4. PBT Notes (Hypothesis)
- Hypothesis runs 50-200 examples per property by default
- On failure: Hypothesis prints the shrunk minimal failing input + seed
- To reproduce a specific failure: `@settings(database=None)` and set `HYPOTHESIS_SEED=<seed>`

## Test Coverage Areas

| Test File | Unit | Coverage |
|-----------|------|---------|
| test_conductor.py | U3 | run(), input validation, error handler, offline pipeline |
| test_context_layering.py | U2 | build_context_packet(), assemble_prompt(), aliases |
| test_failure_diagnostics.py | U2 | All 4 categories, DuckDB error_type, never-raises |
| test_memory.py | U3 | Lazy init, save_turn(), session cap, get_memory_context() |
| test_properties.py | All | ContextPacket round-trip, TraceEvent round-trip, classify invariant, pass@1 range |
