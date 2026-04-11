# U5 Code Generation Summary

**Unit**: U5 — Utilities & Adversarial Probes  
**Status**: Complete  
**Generated**: 2026-04-11

---

## Files Generated

### Shared Infrastructure

| File | Purpose |
|---|---|
| `agent/__init__.py` | Package marker |
| `agent/models.py` | All shared Pydantic models and dataclasses (JoinKeyFormat, JoinKeyFormatResult, CorrectionEntry, ProbeEntry, DBSchema, SchemaContext, BenchmarkResult, DABQuery, TraceStep, KeywordScore) |
| `agent/config.py` | pydantic-settings Settings singleton with all env vars and db_timeouts property |
| `requirements.txt` | Pinned production and test dependencies |
| `pyproject.toml` | Project config, mypy strict settings, pytest markers |
| `.env.example` | Required environment variables with placeholder values |
| `tools.yaml` | MCP Toolbox configuration for all 4 databases |

### Utilities

| File | Purpose | Key Rules |
|---|---|---|
| `utils/join_key_utils.py` | Pure functions: detect_format, transform_key, build_transform_expression | JKU-01 through JKU-07 |
| `utils/multi_pass_retriever.py` | 3-pass corrections retrieval with IDF scoring | MPR-01 through MPR-07 |
| `utils/schema_introspector.py` | Bulkhead-timeout DB introspection for all 4 DB types | SI-01 through SI-03 |
| `utils/benchmark_wrapper.py` | Simplified DAB query API (run_subset, run_single, run_category) | BW-01, BW-02 |

### Adversarial Probes

| File | Purpose |
|---|---|
| `probes/__init__.py` | Package marker |
| `probes/probes.md` | 15 adversarial probes across 4 categories (ROUTING×4, JOIN_KEY×4, TEXT_EXTRACT×4, DOMAIN_GAP×3) |
| `probes/probe_runner.py` | load_probes(), run_probe(), run_post_fix(), run_all(), CLI entrypoint |

### Tests

| File | Purpose | Test Count |
|---|---|---|
| `tests/__init__.py` | Package marker | — |
| `tests/unit/__init__.py` | Package marker | — |
| `tests/integration/__init__.py` | Package marker | — |
| `tests/unit/strategies.py` | Hypothesis strategy factory (INVARIANT_SETTINGS, @st.composite strategies, validate_sql_expression) | — |
| `tests/unit/test_join_key_utils.py` | Unit + 5 blocking PBT properties (PBT-U5-01 through PBT-U5-05) | ~35 |
| `tests/unit/test_multi_pass_retriever.py` | Unit + PBT (count ≤10, dedup, idempotency) | ~20 |
| `tests/unit/test_schema_introspector.py` | Mocked MCPClient; all 4 DB introspectors; graceful degradation | ~20 |
| `tests/unit/test_probe_runner.py` | Mocked agent HTTP; load_probes count; pass threshold | ~25 |
| `tests/integration/test_schema_introspection_live.py` | Live MCP Toolbox; @pytest.mark.integration; auto-skip if unreachable | ~10 |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `detect_format(list[Any]) → JoinKeyFormatResult` | Multi-sample voting with primary+secondary formats; more robust than single-value classification |
| `_UNSUPPORTED_TRANSFORMS` frozenset | NullReturnGuard pattern: unsupported pairs return None, never raise |
| IDF gate at corpus ≥20 | Static tiers are the baseline; IDF kicks in only when corpus is statistically meaningful |
| MCPClient Protocol | Dependency injection for SchemaIntrospector testability without real MCP Toolbox |
| Outer 9s + per-DB sub-limits | Bulkhead pattern: MongoDB=4s, PostgreSQL=2.5s, DuckDB=1.5s, SQLite=1s; sum ≤9s |
| `return_exceptions=True` in asyncio.gather | Partial failures return DBSchema with error field; never block startup |
| All 15 probes in Markdown tables | Parseable by probe_runner.py regex; human-readable alongside code |

---

## PBT Invariant Properties

| ID | Description | Max Examples | Deadline |
|---|---|---|---|
| PBT-U5-01 | Round-trip: INTEGER → PREFIXED_STRING → INTEGER returns original | 200 | 500ms |
| PBT-U5-02 | Output constraint: detect_format always returns JoinKeyFormatResult with correct primary | 200 | 500ms |
| PBT-U5-03 | Idempotency: same inputs → same outputs (detect_format and transform_key) | 100 | 200ms |
| PBT-U5-04 | Monotonicity: strict majority format always wins primary | 100 | 500ms |
| PBT-U5-05 | Expression validity: no unresolved placeholders, dialect-appropriate functions | 150 | 200ms |

---

## Dependencies on Other Units

| Dependency | Status | Notes |
|---|---|---|
| U2 (ExecutionEngine) | Not yet built | benchmark_wrapper uses lazy import of EvaluationHarness |
| U4 (EvaluationHarness) | Not yet built | benchmark_wrapper.run_subset lazy-imports harness inside function |
| MCP Toolbox | External process | SchemaIntrospector uses AiohttpMCPClient in production; MCPClient Protocol in tests |
