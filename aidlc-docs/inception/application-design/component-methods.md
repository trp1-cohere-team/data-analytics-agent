# Component Methods
# The Oracle Forge — Data Analytics Agent

**Date**: 2026-04-11  
**Note**: Method signatures define interfaces. Detailed business rules are specified in Functional Design (Construction Phase).

---

## AgentAPI

```python
# agent/api/app.py

async def handle_query(request: QueryRequest) -> QueryResponse:
    """POST /query — Main entry point. Validates input, creates session, delegates to Orchestrator."""
    # Input: QueryRequest(question: str, databases: list[str] | None, session_id: str | None)
    # Output: QueryResponse(answer: Any, query_trace: list[TraceStep], confidence: float, session_id: str)

async def health_check() -> HealthResponse:
    """GET /health — Returns server status and MCP Toolbox reachability."""
    # Output: HealthResponse(status: str, mcp_toolbox: bool, databases: dict[str, bool])

async def get_schema_info() -> SchemaResponse:
    """GET /schema — Returns cached Layer 1 schema context."""
    # Output: SchemaResponse(databases: dict[str, TableList])
```

---

## Orchestrator

```python
# agent/orchestrator/react_loop.py

async def run(
    query: str,
    session_id: str,
    context: ContextBundle,
    max_iterations: int = 10,
    confidence_threshold: float = 0.85,
) -> OrchestratorResult:
    """Execute the ReAct loop for a given query and context bundle.
    Returns when FINAL_ANSWER action is produced or max_iterations reached."""

async def think(state: ReactState) -> Thought:
    """Single ReAct 'think' step: calls LLM with current state, returns structured thought.
    Thought includes: reasoning, chosen_action, action_input."""

async def act(thought: Thought, context: ContextBundle) -> Observation:
    """Execute the action chosen in 'think': dispatches to tool (DB query, KB search, etc.).
    Returns raw observation from the tool."""

def observe(observation: Observation, state: ReactState) -> ReactState:
    """Update state with the latest observation. Check termination condition."""

async def _call_llm(messages: list[dict], tools: list[dict]) -> LLMResponse:
    """OpenRouter GPT-4o call. Handles retries on rate limit (max 3 with exponential backoff)."""
```

---

## ContextManager

```python
# agent/context/manager.py

async def startup_load() -> None:
    """Called once at server startup. Loads Layer 1 (schema) into permanent cache.
    Starts background task for Layer 2 file-watch."""

async def get_context_bundle(session_id: str) -> ContextBundle:
    """Assembles all three layers for a session.
    Layer 1: from in-memory cache.
    Layer 2: from in-memory cache (refreshed if file mtime changed).
    Layer 3: loaded fresh from kb/corrections/ for this session."""

async def _refresh_layer2_if_stale() -> None:
    """Background task (runs every 60s). Checks KB file mtimes.
    If any changed, reloads domain KB documents into Layer 2 cache."""

def _load_layer3(session_id: str) -> CorrectionsContext:
    """Reads kb/corrections/corrections.json. Returns last N corrections as CorrectionsContext.
    Never cached; always reads from disk."""

async def invalidate_layer2_cache() -> None:
    """Force-reload Layer 2 (used after KB update in tests)."""
```

---

## CorrectionEngine

```python
# agent/correction/engine.py

async def correct(
    failure: ExecutionFailure,
    original_query: str,
    context: ContextBundle,
    attempt: int = 1,
) -> CorrectionResult:
    """Main entry point. Classifies failure, applies cheapest fix.
    Raises CorrectionExhausted if attempt > 3."""

def classify_failure(failure: ExecutionFailure) -> FailureType:
    """Rule-based classifier. Returns one of:
    SYNTAX_ERROR | JOIN_KEY_MISMATCH | WRONG_DB_TYPE | DATA_QUALITY | UNKNOWN"""

def fix_syntax_error(query: str, error: str) -> str:
    """Rule-based query rewriter for common syntax errors (no LLM).
    Handles: missing quotes, wrong aggregate syntax, dialect differences."""

def fix_join_key(query: str, mismatch: JoinKeyMismatch) -> str:
    """Rewrites JOIN condition with key format transformation (no LLM).
    Uses JoinKeyUtils to detect and apply the correct format conversion."""

def fix_wrong_db_type(plan: QueryPlan, error: ExecutionFailure) -> QueryPlan:
    """Updates db_type routing in the query plan (no LLM).
    Detects from error signals which DB was wrong and reroutes."""

def fix_data_quality(query: str, error: ExecutionFailure) -> str:
    """Adds COALESCE / IFNULL / null-guard to handle missing fields (no LLM)."""

async def llm_correct(query: str, error: str, context: ContextBundle) -> str:
    """Last-resort LLM corrector. Sends error + original query to GPT-4o.
    Prompt includes schema context and corrections log."""
```

---

## MultiDBEngine

```python
# agent/execution/engine.py

async def execute_plan(plan: QueryPlan) -> ExecutionResult:
    """Top-level executor. Dispatches sub-queries, resolves join keys, merges results."""

async def route_and_execute(sub_query: SubQuery) -> SubQueryResult:
    """Routes one sub-query to the correct DB connector based on sub_query.db_type."""

async def execute_postgres(query: str, params: dict) -> SubQueryResult:
    """Calls MCP Toolbox tool 'postgres_query' via HTTP. Returns structured result."""

async def execute_sqlite(query: str, params: dict) -> SubQueryResult:
    """Calls MCP Toolbox tool 'sqlite_query' via HTTP."""

async def execute_mongodb(pipeline: list[dict], collection: str) -> SubQueryResult:
    """Calls MCP Toolbox tool 'mongodb_aggregate' via HTTP."""

async def execute_duckdb(query: str, params: dict) -> SubQueryResult:
    """Calls MCP Toolbox tool 'duckdb_query' via HTTP."""

def resolve_join_keys(plan: QueryPlan) -> QueryPlan:
    """Pre-execution step. For each cross-DB join, detects key format mismatch
    and rewrites the join condition using JoinKeyUtils."""

def merge_results(results: list[SubQueryResult], merge_spec: MergeSpec) -> MergedResult:
    """Merges sub-query results into a single result set per MergeSpec (join keys, aggregation)."""
```

---

## KnowledgeBase

```python
# agent/kb/knowledge_base.py

def get_architecture_docs() -> list[KBDocument]:
    """Reads all *.md files from kb/architecture/. Returns list of KBDocument."""

def get_domain_docs() -> list[KBDocument]:
    """Reads all *.md files from kb/domain/. Returns list of KBDocument."""

def get_evaluation_docs() -> list[KBDocument]:
    """Reads all *.md files from kb/evaluation/."""

def get_corrections(limit: int = 50) -> list[CorrectionEntry]:
    """Reads kb/corrections/corrections.json. Returns last N entries."""

def append_correction(entry: CorrectionEntry) -> None:
    """Appends one correction entry to kb/corrections/corrections.json.
    Also updates kb/corrections/CHANGELOG.md."""

def update_changelog(subdir: str, change: str) -> None:
    """Appends entry to CHANGELOG.md in the given KB subdirectory."""
```

---

## MemoryManager

```python
# agent/memory/manager.py

def load_session_memory(session_id: str) -> SessionMemory:
    """Loads MEMORY.md index, then reads topic files referenced by index.
    Returns SessionMemory with successful_patterns, user_preferences, corrections."""

def write_session_transcript(session_id: str, transcript: list[TraceStep]) -> None:
    """Writes session trace to agent/memory/sessions/{session_id}.json."""

def update_memory_index(new_topic_file: str) -> None:
    """Appends pointer to new topic file in MEMORY.md index."""

def consolidate_old_sessions(max_age_days: int = 7) -> None:
    """autoDream: reads sessions older than max_age_days, extracts patterns,
    merges into topic files, deletes raw session files."""
```

---

## EvaluationHarness

```python
# eval/harness.py

async def run_benchmark(
    agent_url: str,
    queries: list[DABQuery],
    n_trials: int = 50,
    output_path: str = "results/",
) -> BenchmarkResult:
    """Runs agent on all queries × n_trials. Returns BenchmarkResult with per-query scores."""

def score_exact_match(result: Any, expected: Any, tolerance: float = 1e-4) -> bool:
    """Exact match scorer with numeric float tolerance and string normalization."""

async def score_llm_judge(result: Any, expected: Any, question: str) -> JudgeVerdict:
    """LLM-as-judge scorer. Returns JudgeVerdict(passed: bool, rationale: str, confidence: float)."""

def record_trace(session_id: str, trace: list[TraceStep]) -> None:
    """Writes query trace to results/traces/{session_id}.json."""

async def run_regression_suite(agent_url: str, held_out_path: str) -> RegressionResult:
    """Runs agent on held-out test set. Asserts pass@1 >= previous run score (from score log)."""

def append_score_log(run_result: BenchmarkResult) -> None:
    """Appends one line to results/score_log.jsonl (JSON Lines, append-only)."""
```

---

## SharedUtils — SchemaIntrospector

```python
# utils/schema_introspector.py

async def introspect_all(mcp_toolbox_url: str) -> SchemaContext:
    """Calls MCP Toolbox to introspect all connected databases.
    Returns SchemaContext with table/collection schemas per database."""

async def introspect_postgres(db_name: str) -> DBSchema:
    """Queries information_schema for tables, columns, types, foreign keys."""

async def introspect_sqlite(db_path: str) -> DBSchema:
    """Queries sqlite_master for table and column metadata."""

async def introspect_mongodb(db_name: str) -> DBSchema:
    """Samples 100 documents per collection to infer schema."""

async def introspect_duckdb(db_path: str) -> DBSchema:
    """Queries PRAGMA and information_schema for DuckDB schema."""
```

---

## SharedUtils — MultiPassRetriever

```python
# utils/multi_pass_retriever.py

def retrieve_corrections(
    query: str,
    corrections: list[CorrectionEntry],
    passes: int = 3,
) -> list[CorrectionEntry]:
    """Runs N vocabulary passes over corrections log (corrected, pushed back, disagreed, etc.).
    Deduplicates and returns ranked matches most relevant to query."""

def _build_pass_queries(query: str) -> list[str]:
    """Generates N vocabulary variations for multi-pass search.
    Pass 1: failure/error/wrong terms. Pass 2: correction/fix/resolved terms.
    Pass 3: domain-specific terms extracted from the query."""
```

---

## SharedUtils — JoinKeyUtils

```python
# utils/join_key_utils.py

def detect_format(key_sample: Any) -> JoinKeyFormat:
    """Detects key format from a sample value.
    Returns: INTEGER | PREFIXED_STRING | UUID | COMPOSITE | UNKNOWN"""

def transform_key(value: Any, source_fmt: JoinKeyFormat, target_fmt: JoinKeyFormat) -> Any:
    """Transforms a key value from source format to target format.
    E.g. integer 1234 → 'CUST-01234' (PREFIXED_STRING with 5-digit zero-padding)."""

def build_transform_expression(
    source_column: str,
    source_fmt: JoinKeyFormat,
    target_fmt: JoinKeyFormat,
    db_type: str,
) -> str:
    """Returns a SQL/MQL expression that transforms the join key in-query.
    E.g. for PostgreSQL: LPAD(CAST(customer_id AS TEXT), 5, '0') for integer→zero-padded."""
```
