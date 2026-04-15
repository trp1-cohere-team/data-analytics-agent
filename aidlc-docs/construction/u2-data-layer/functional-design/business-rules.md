# Business Rules — U2 Data Layer

---

## BR-U2-01: Unified Tool Interface
**Rule**: All upstream components (ToolRegistry, conductor, planner, synthesizer) interact with `MCPClient` ONLY. No upstream component imports `DuckDBBridgeClient` or `duckdb_bridge_client.py`.
- `discover_tools()` returns a flat 4-tool list; callers cannot distinguish which backend serves which tool
- `invoke_tool()` dispatches internally by `kind` — the routing is invisible to callers
- **Enforcement**: Import rule in unit-of-work-dependency.md

---

## BR-U2-02: tools.yaml as Single Source of Truth
**Rule**: `MCPClient` reads `tools.yaml` at init to build its 4-tool registry. The registry is NOT hardcoded — it is derived from the YAML file.
- In offline mode, the registry is built from `OFFLINE_TOOL_LIST` (which mirrors tools.yaml structure)
- No tool is added or removed at runtime — the registry is immutable after init
- **Enforcement**: FR-03

---

## BR-U2-03: DuckDB Dispatch Correctness
**Rule**: Within `MCPClient`, any tool with `kind == "duckdb_bridge_sql"` MUST be dispatched to `DuckDBBridgeClient`. Any tool with standard kinds MUST be dispatched to Google MCP Toolbox. No cross-routing is permitted.
- DuckDB bridge client validates `db_type == "duckdb"` (SEC-05)
- **Enforcement**: PBT-03 invariant test

---

## BR-U2-04: Context Layer Precedence
**Rule**: When assembling a prompt from `ContextPacket`, Layer 6 (user_question) always takes highest precedence, appearing first. Layer 1 (table_usage) takes lowest precedence, appearing last.
- Partial layers are allowed — empty layers are omitted from assembly
- `runtime_context` (dict) is serialized to formatted text before inclusion
- **Enforcement**: FR-02, PBT-03 invariant

---

## BR-U2-05: Failure Classification Completeness
**Rule**: `classify()` MUST always return a valid `FailureDiagnosis`. It MUST never raise an exception or return None. The default fallback category is `"query"`.
- The 4 valid categories: `query`, `join-key`, `db-type`, `data-quality`
- DuckDB bridge `error_type` field maps deterministically to categories
- **Enforcement**: FR-04, PBT-03 invariant

---

## BR-U2-06: KB Retrieval Scoring
**Rule**: Document relevance scoring uses a weighted formula:
`final_score = 0.6 * content_score + 0.25 * filename_score + 0.15 * freshness`
- All component scores are in [0.0, 1.0] or [0.0, 0.3]
- Documents with score == 0.0 are excluded from results
- Results sorted by descending score
- **Enforcement**: FR-09

---

## BR-U2-07: Read-Only Enforcement (Defense in Depth)
**Rule**: Before sending SQL to any backend, the system should block mutation keywords as a defense-in-depth measure.
- Primary enforcement: Bridge server-side / Google MCP Toolbox read-only mode
- Secondary enforcement: `ToolPolicy` in U3 blocks INSERT/UPDATE/DELETE/DROP/CREATE/ALTER
- DuckDB bridge additionally enforces read-only server-side
- **Enforcement**: SEC-05, SEC-11

---

## BR-U2-08: Offline Mode Completeness
**Rule**: When `AGENT_OFFLINE_MODE=1`, all U2 modules MUST function without any HTTP calls.
- `MCPClient`: uses `OFFLINE_TOOL_LIST` and `OFFLINE_INVOKE_RESULTS`
- `DuckDBBridgeClient`: uses same offline stubs keyed by `"duckdb"`
- `knowledge_base.py`: reads local files only (no network dependency)
- `failure_diagnostics.py`: pure computation, no network
- `context_layering.py`: pure computation, no network
- **Enforcement**: NFR-01

---

## Testable Properties (PBT-01)

### Round-Trip Properties (PBT-02)
| Component | Property |
|---|---|
| `ContextPacket` build + serialize | `ContextPacket.from_dict(build_context_packet(...).to_dict())` preserves all layers |

### Invariant Properties (PBT-03)
| Component | Invariant |
|---|---|
| `classify()` | Always returns category in `{"query", "join-key", "db-type", "data-quality"}` |
| Context layer precedence | Layer 6 content always before Layer 1 in assembled prompt |
| `score_overlap()` result | Always in [0.0, 1.0] (inherited from U1, tested here with KB contexts) |
| DuckDB dispatch | `kind=="duckdb_bridge_sql"` always routed to DuckDBBridgeClient |

---

## Security Compliance Summary (U2 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| SECURITY-03 | Compliant | All modules use `logging.getLogger(__name__)`; SQL queries logged via `sanitize_sql_for_log()` |
| SECURITY-05 | Compliant | DuckDB bridge validates sql length; tool params validated before dispatch |
| SECURITY-09 | Compliant | Generic error messages; no bridge URLs or file paths in error responses |
| SECURITY-10 | N/A | Supply chain managed in U5 |
| SECURITY-11 | Compliant | MCPClient facade isolates dispatch logic; DuckDB bridge is defense-in-depth layer |
| SECURITY-13 | Compliant | YAML parsing via `yaml.safe_load()`; JSON via `json.loads()` with try/except |
| SECURITY-15 | Compliant | All HTTP calls have explicit try/except; timeouts enforced; resources released |

## PBT Compliance Summary (U2 Functional Design)

| Rule | Status | Rationale |
|---|---|---|
| PBT-01 | Compliant | Testable properties identified (1 round-trip, 4 invariants) |
| PBT-02 | Compliant (design) | ContextPacket round-trip documented |
| PBT-03 | Compliant (design) | classify() invariant, precedence invariant, DuckDB dispatch invariant |
| PBT-07 | N/A | Generator quality at code generation |
| PBT-08 | N/A | Shrinking/reproducibility at code generation |
| PBT-09 | N/A | Framework already selected |
