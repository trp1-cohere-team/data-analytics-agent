# U5 Code Generation Plan
# Unit 5 — Utilities & Adversarial Probes

**Status**: Complete  
**Date**: 2026-04-11  
**Workspace Root**: `c:/Users/Administrator/Desktop/TRP1/TRP1-coursework/week-08/data-analytics-agent/`

---

## Unit Context

| Item | Detail |
|---|---|
| Unit | U5 — Utilities & Adversarial Probes |
| Build order | 1st (no unit dependencies) |
| Dependencies | `agent/models.py`, `agent/config.py` (shared infra, created in this unit) |
| Consumed by | U1 (imports JoinKeyUtils, MultiPassRetriever, SchemaIntrospector), U2 (imports JoinKeyUtils) |
| Requirements covered | FR-05, FR-09, FR-11, NFR-05 (PBT) |
| Extensions | Security Baseline (N/A for utilities), PBT (blocking — 5 invariant properties) |

---

## Requirements Traceability

| Req | Covered By |
|---|---|
| FR-05 Join key resolution | Step 4 — `utils/join_key_utils.py` |
| FR-09 ≥15 adversarial probes, ≥3 categories | Step 8 — `probes/probes.md` + `probes/probe_runner.py` |
| FR-11 MCP Toolbox integration | Step 6 — `utils/schema_introspector.py` |
| FR-10 Repository structure | Step 1 — project structure setup |
| NFR-05 PBT full invariant suite | Steps 9–10 — `tests/unit/strategies.py` + `test_join_key_utils.py` |

---

## Generation Steps

### Step 1: Project Structure Setup
**Files**:
- `utils/__init__.py`
- `probes/__init__.py`
- `agent/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/integration/__init__.py`
- `requirements.txt` — all pinned dependencies (hypothesis, aiohttp, pydantic, fastapi, openai, slowapi, pytest, pytest-asyncio, mypy, safety)
- `pyproject.toml` — project metadata, tool config (mypy strict, pytest settings)
- `.env.example` — all required env vars with placeholder values
- `tools.yaml` — MCP Toolbox configuration (all 4 DBs)
- [x] Step 1 complete

### Step 2: Shared Infrastructure — `agent/models.py`
All shared Pydantic v2 models and dataclasses used across unit boundaries:
- `JoinKeyFormat` (Enum), `JoinKeyFormatResult` (frozen dataclass)
- `ColumnSchema`, `ForeignKeyRelationship`, `TableSchema`, `DBSchema`, `SchemaContext`
- `CorrectionEntry`, `KeywordScore` (dataclass, internal)
- `QueryRequest`, `QueryResponse`, `HealthResponse`, `SchemaResponse`
- `QueryPlan`, `SubQuery`, `MergeSpec`, `ExecutionResult`, `SubQueryResult`, `ExecutionFailure`
- `ContextBundle`, `DomainContext`, `CorrectionsContext`
- `KBDocument`, `ReactState`, `Thought`, `Observation`, `TraceStep`, `OrchestratorResult`
- `SessionMemory`, `FailureType`, `JoinKeyMismatch`, `CorrectionResult`
- `BenchmarkResult`, `DABQuery`, `JudgeVerdict`, `RegressionResult`
- `ProbeEntry` (all fields from Full schema — Option C)
- [x] Step 2 complete

### Step 3: Shared Infrastructure — `agent/config.py`
`pydantic-settings` `Settings` class reading from `.env` + environment:
- All config fields with defaults (OPENROUTER_*, MCP_TOOLBOX_URL, AGENT_PORT, rate limits, timeouts, thresholds)
- `DB_TIMEOUTS: dict[str, float]` = {mongodb: 4.0, postgres: 2.5, duckdb: 1.5, sqlite: 1.0}
- `OUTER_INTROSPECT_TIMEOUT: float` = 9.0
- Singleton `settings = Settings()` exported at module level
- [x] Step 3 complete

### Step 4: `utils/join_key_utils.py`
Implements all 3 public functions + internal components:
- Module-level compiled regex constants (`_DIGITS_RE`, `_PREFIXED_RE`, `_UUID_RE`)
- `UNSUPPORTED_TRANSFORMS` set (13 unsupported pairs)
- `_classify_single(value: Any) -> JoinKeyFormat` — decision tree per domain-entities.md
- `detect_format(key_samples: list[Any]) -> JoinKeyFormatResult` — single-sample fallback + MajorityVoter
- `transform_key(value: Any, source_fmt: JoinKeyFormat, target_fmt: JoinKeyFormat) -> Any` — NullReturnGuard + transformation table
- `build_transform_expression(source_column: str, source_fmt: JoinKeyFormat, target_fmt: JoinKeyFormat, db_type: str) -> str | None` — dialect dispatch table per nfr-design logical-components.md
- [x] Step 4 complete

### Step 5: `utils/multi_pass_retriever.py`
- `PASS1_BASE`, `PASS2_BASE`, `STOP_WORDS` frozen sets
- `HIGH_VALUE_TERMS` set for keyword tier scoring
- `_keyword_tier_score(keyword: str) -> int` — returns 3 or 1
- `_compute_idf(corrections: list[CorrectionEntry]) -> dict[str, float]` — IDF gate at ≥20 entries
- `_build_pass_queries(query: str) -> list[list[str]]` — 3 passes with domain term extraction
- `retrieve_corrections(query: str, corrections: list[CorrectionEntry], passes: int = 3) -> list[CorrectionEntry]` — accumulator pattern, dedup, rank, cap 10
- [x] Step 5 complete

### Step 6: `utils/schema_introspector.py`
- `DB_TIMEOUTS` imported from `agent/config`
- `_bulkhead_gather(tasks, outer_timeout) -> dict[str, DBSchema | BaseException]` — outer + per-DB timeouts, `return_exceptions=True`
- `_assemble_schema(results) -> SchemaContext` — GracefulSchemaAssembler, maps exceptions to error field
- `introspect_postgres(db_name: str, client: aiohttp.ClientSession) -> DBSchema` — 3 SQL queries via MCP Toolbox
- `introspect_sqlite(db_path: str, client: aiohttp.ClientSession) -> DBSchema` — PRAGMA queries
- `introspect_mongodb(db_name: str, client: aiohttp.ClientSession) -> DBSchema` — sample 100 docs per collection
- `introspect_duckdb(db_path: str, client: aiohttp.ClientSession) -> DBSchema` — information_schema + PRAGMA
- `introspect_all(mcp_toolbox_url: str) -> SchemaContext` — orchestrates bulkhead gather
- HTTP client injected (not hardcoded) for testability
- [x] Step 6 complete

### Step 7: `utils/benchmark_wrapper.py`
- `load_dab_queries(filter=None) -> list[DABQuery]` — reads DAB query set from `signal/` or `eval/` directory
- `run_subset(agent_url: str, query_ids: list[str], trials: int = 5) -> BenchmarkResult`
- `run_single(agent_url: str, query_id: str, trials: int = 3) -> BenchmarkResult`
- `run_category(agent_url: str, category: str, trials: int = 5) -> BenchmarkResult`
- Delegates to `EvaluationHarness.run_benchmark` (imported lazily to avoid circular import with U4)
- [x] Step 7 complete

### Step 8: ProbeLibrary — `probes/probes.md` + `probes/probe_runner.py`
**probes/probes.md**:
- 15 probe entries in Markdown table format
- Coverage: ROUTING×4, JOIN_KEY×4, TEXT_EXTRACT×4, DOMAIN_GAP×3
- All fields per ProbeEntry Full schema: id, category, query, description, expected_failure_mode, db_types_involved, fix_applied, error_signal, correction_attempt_count, observed_agent_response, pre_fix_score, post_fix_score, post_fix_pass

**probes/probe_runner.py**:
- `load_probes(path: str = "probes/probes.md") -> list[ProbeEntry]` — parse Markdown table
- `score_response(response: dict, expected_failure_mode: str) -> float`
- `extract_error_signal(query_trace: list[TraceStep]) -> str | None`
- `run_probe(probe_entry: ProbeEntry, agent_url: str) -> ProbeEntry` — pre-fix run, record, post-fix run, record
- `run_all(agent_url: str, category: str | None = None) -> list[ProbeEntry]`
- CLI: `python probes/probe_runner.py --agent-url http://localhost:8000 [--category ROUTING]`
- [x] Step 8 complete

### Step 9: `tests/unit/strategies.py`
Hypothesis strategy factory for all PBT tests:
- `integer_keys(draw, min_val=1, max_val=999_999) -> int`
- `prefixed_keys(draw, prefix=None, width=None) -> str`
- `uuid_keys(draw) -> str`
- `key_samples_with_majority(draw, primary_fmt, minority_fmts=None, n=None) -> list`
- `strategy_for(fmt: JoinKeyFormat) -> SearchStrategy` — dispatcher
- `INVARIANT_SETTINGS` dict with per-property Hypothesis settings
- `validate_sql_expression(expr, source_column, db_type) -> bool` — SqlExpressionValidator
- [x] Step 9 complete

### Step 10: `tests/unit/test_join_key_utils.py`
Unit tests + 5 blocking PBT properties:
- Unit tests: `_classify_single` for all 5 format paths + UNKNOWN + edge cases (empty string, None, float)
- Unit tests: `transform_key` for all supported pairs + all unsupported pairs returning None + identity (src==tgt)
- Unit tests: `build_transform_expression` for all 4 dialects + None on unsupported
- **PBT-U5-01**: Round-trip `@given(prefixed_keys()) @settings(INVARIANT_SETTINGS["PBT-U5-01"])`
- **PBT-U5-02**: Output constraint `@given(integer_keys() | prefixed_keys())`
- **PBT-U5-03**: Idempotency `@given(integer_keys() | prefixed_keys())`
- **PBT-U5-04**: Monotonicity `@given(key_samples_with_majority(...))`
- **PBT-U5-05**: Expression validity `@given(integer_keys() | prefixed_keys(), st.sampled_from(["postgres","sqlite","duckdb","mongodb"]))`
- [x] Step 10 complete

### Step 11: `tests/unit/test_multi_pass_retriever.py`
- `_build_pass_queries`: verifies 3 lists returned, Pass 3 contains domain terms from query
- `_keyword_tier_score`: HIGH_VALUE_TERMS score 3, others score 1
- `_compute_idf`: returns empty dict when corpus < 20; returns non-empty when ≥20
- `retrieve_corrections`: deduplication, cap at 10, recency tiebreaker, IDF gate behaviour
- PBT: `@given(st.lists(correction_entries(), min_size=0, max_size=50))` — result count always ≤ 10, all scores ≥ 0
- [x] Step 11 complete

### Step 12: `tests/unit/test_schema_introspector.py`
Mock HTTP client injected; no real MCP Toolbox required:
- `introspect_all` success: all 4 DBs return valid schemas
- `introspect_all` partial timeout: timed-out DBs have empty schema + error field; others present
- `introspect_all` outer ceiling: all DBs timeout → full empty SchemaContext, no exception raised
- `_assemble_schema`: all exception types mapped to correct error strings
- Parameterised tests for each DB type (postgres/sqlite/mongodb/duckdb)
- [x] Step 12 complete

### Step 13: `tests/unit/test_probe_runner.py`
Mock HTTP client replacing live agent:
- `load_probes`: parses probes.md and returns correct count (≥15)
- `run_probe`: pre-fix score recorded, post-fix score recorded, `post_fix_pass` set correctly at threshold 0.8
- `score_response`: various response shapes
- `extract_error_signal`: extracts from trace correctly; returns None when absent
- [x] Step 13 complete

### Step 14: `tests/integration/test_schema_introspection_live.py`
Requires real MCP Toolbox running (marked with `@pytest.mark.integration`):
- `test_introspect_all_returns_nonempty_schema` — at least 1 DB returns tables
- `test_introspect_all_within_timeout` — completes in < 10s
- `test_partial_failure_graceful` — with one DB deliberately misconfigured, others still introspected
- [x] Step 14 complete

### Step 15: Code Summary — `aidlc-docs/construction/u5-utilities-probes/code/code-summary.md`
Markdown summary of all generated files, line counts, key decisions, known limitations.
- [x] Step 15 complete

---

## Total: 15 steps | ~20 files created
