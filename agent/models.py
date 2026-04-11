"""Shared data models for The Oracle Forge agent.

All Pydantic models and dataclasses used across unit boundaries are defined here.
Units import from this module — never define shared types locally.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# JoinKeyUtils
# ---------------------------------------------------------------------------

class JoinKeyFormat(str, Enum):
    """Structural format of a database join key column."""
    INTEGER = "INTEGER"
    PREFIXED_STRING = "PREFIXED_STRING"
    UUID = "UUID"
    COMPOSITE = "COMPOSITE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class JoinKeyFormatResult:
    """Result of multi-sample format detection.

    Invariants:
    - primary_format is always set (never None)
    - secondary_formats never contains UNKNOWN
    - secondary_formats never contains primary_format
    - secondary_formats is an empty list (not None) when no minority formats
    """
    primary_format: JoinKeyFormat
    secondary_formats: list[JoinKeyFormat] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema Introspection
# ---------------------------------------------------------------------------

class ColumnSchema(BaseModel):
    """Metadata for one column or field within a table or collection."""
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool


class ForeignKeyRelationship(BaseModel):
    """FK constraint or inferred relationship between two columns."""
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class TableSchema(BaseModel):
    """Full schema metadata for one table or MongoDB collection."""
    name: str
    columns: list[ColumnSchema] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyRelationship] = Field(default_factory=list)


class DBSchema(BaseModel):
    """Complete schema for one database."""
    db_name: str
    db_type: str  # "postgres" | "sqlite" | "mongodb" | "duckdb"
    tables: list[TableSchema] = Field(default_factory=list)
    error: str | None = None


class SchemaContext(BaseModel):
    """Aggregated schema for all connected databases (Layer 1 context)."""
    databases: dict[str, DBSchema] = Field(default_factory=dict)
    loaded_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

class CorrectionEntry(BaseModel):
    """One record in the corrections log."""
    id: str
    timestamp: float
    session_id: str
    failure_type: str  # SYNTAX_ERROR | JOIN_KEY_MISMATCH | WRONG_DB_TYPE | DATA_QUALITY | UNKNOWN
    original_query: str
    corrected_query: str | None = None
    error_message: str
    fix_strategy: str  # rule_syntax | rule_join_key | rule_db_type | rule_null_guard | llm_corrector
    attempt_number: int
    success: bool

    def searchable_text(self) -> str:
        """Return concatenated text fields for keyword matching."""
        parts = [self.original_query, self.failure_type, self.error_message]
        if self.corrected_query:
            parts.append(self.corrected_query)
        return " ".join(parts).lower()


@dataclass
class KeywordScore:
    """Intermediate scoring structure used during retrieve_corrections. Not persisted."""
    entry_id: str
    raw_score: float
    timestamp: float
    entry: CorrectionEntry


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

class ProbeEntry(BaseModel):
    """One adversarial probe definition and recorded results."""
    id: str                        # e.g. "ROUTING-001"
    category: str                  # ROUTING | JOIN_KEY | TEXT_EXTRACT | DOMAIN_GAP
    query: str
    description: str
    expected_failure_mode: str
    db_types_involved: list[str]
    fix_applied: str
    error_signal: str | None = None
    correction_attempt_count: int | None = None
    observed_agent_response: str | None = None
    pre_fix_score: float | None = None
    post_fix_score: float | None = None
    post_fix_pass: bool | None = None


# ---------------------------------------------------------------------------
# API Layer
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Inbound request to POST /query."""
    question: str = Field(min_length=1, max_length=4096)
    databases: list[str] | None = None
    session_id: str | None = None


class TraceStep(BaseModel):
    """One iteration of the ReAct loop recorded for tracing."""
    iteration: int
    thought: str
    action: str
    action_input: dict[str, Any] = Field(default_factory=dict)
    observation: str
    timestamp: float


class QueryResponse(BaseModel):
    """Response from POST /query."""
    answer: Any
    query_trace: list[TraceStep] = Field(default_factory=list)
    confidence: float
    session_id: str


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    mcp_toolbox: bool
    databases: dict[str, bool] = Field(default_factory=dict)


class SchemaResponse(BaseModel):
    """Response from GET /schema."""
    databases: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Execution Engine
# ---------------------------------------------------------------------------

class SubQuery(BaseModel):
    """One sub-query targeting a specific database."""
    id: str                                          # UUID unique within the plan
    db_type: str                                     # "postgres" | "sqlite" | "mongodb" | "duckdb"
    db_name: str                                     # Target database/file name for routing
    query: str                                       # SQL string; ignored for MongoDB
    pipeline: list[dict[str, Any]] | None = None    # MongoDB aggregation pipeline (pre-built by LLM)
    collection: str | None = None                   # MongoDB collection name
    join_key: str | None = None                     # Column name for cross-DB join; None if not part of a join
    source_join_format: JoinKeyFormat | None = None  # Format of join key in this sub-query's DB
    target_join_format: JoinKeyFormat | None = None  # Format expected by the joining sub-query
    join_key_prefix: str | None = None              # PREFIXED_STRING prefix (e.g. "CUST")
    join_key_width: int | None = None               # Zero-padding width
    join_key_unresolvable: bool = False              # Set by JoinKeyResolver when format pair unsupported


class MergeSpec(BaseModel):
    """Specification for merging sub-query results."""
    strategy: str = "UNION"                # "UNION" | "LEFT_JOIN" | "FIRST_ONLY"
    join_key: str | None = None            # Column name to join on; required for LEFT_JOIN
    left_db_type: str | None = None        # db_type whose result is the left side of LEFT_JOIN


class QueryPlan(BaseModel):
    """Full query plan produced by the Orchestrator for MultiDBEngine."""
    id: str                                          # Plan UUID
    sub_queries: list[SubQuery]
    merge_spec: MergeSpec = Field(default_factory=MergeSpec)


class SubQueryResult(BaseModel):
    """Result from one sub-query execution."""
    sub_query_id: str                                # References SubQuery.id
    db_type: str                                     # Copied from SubQuery.db_type
    rows: list[dict[str, Any]] = Field(default_factory=list)  # Always [] on failure
    row_count: int = 0
    execution_time_ms: float = 0.0                   # Wall-clock time (0.0 on instant error)
    error: str | None = None                         # Error description; None on success
    row_cap_applied: bool = False                    # Stage-1 cap fired

    @property
    def is_success(self) -> bool:
        return self.error is None


class ExecutionResult(BaseModel):
    """Merged result from MultiDBEngine.execute_plan."""
    results: list[SubQueryResult] = Field(default_factory=list)   # One per SubQuery; preserves plan order
    merged_rows: list[dict[str, Any]] = Field(default_factory=list)  # Output of ResultMerger
    failures: list["ExecutionFailure"] = Field(default_factory=list)  # One per failed SubQueryResult
    merge_row_cap_applied: bool = False              # Stage-2 cap fired


class ExecutionFailure(BaseModel):
    """Structured failure for one sub-query — never raised, always returned."""
    sub_query_id: str                                # References the failed SubQuery.id
    db_type: str                                     # Which DB type failed
    error_message: str                               # Human-readable error description
    error_type: str                                  # "timeout" | "connection_error" | "rate_limit" |
                                                     # "auth_error" | "schema_error" | "data_type_error" |
                                                     # "query_error" | "unknown"


# ---------------------------------------------------------------------------
# Orchestrator / ReAct
# ---------------------------------------------------------------------------

class Thought(BaseModel):
    """Output of one ReAct think() step."""
    reasoning: str
    chosen_action: str  # query_database | search_kb | extract_from_text | resolve_join_keys | FINAL_ANSWER
    action_input: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class Observation(BaseModel):
    """Output of one ReAct act() step."""
    action: str
    result: Any
    success: bool
    error: str | None = None


class ReactState(BaseModel):
    """Mutable state threaded through the ReAct loop."""
    query: str
    session_id: str
    iteration: int = 0
    history: list[TraceStep] = Field(default_factory=list)
    terminated: bool = False
    final_answer: Any = None
    confidence: float = 0.0


class OrchestratorResult(BaseModel):
    """Final output of Orchestrator.run()."""
    answer: Any
    query_trace: list[TraceStep]
    confidence: float
    session_id: str
    iterations_used: int


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

class KBDocument(BaseModel):
    """One document loaded from the knowledge base."""
    path: str
    content: str
    subdirectory: str  # architecture | domain | evaluation


class DomainContext(BaseModel):
    """Layer 2 context — domain KB documents."""
    documents: list[KBDocument] = Field(default_factory=list)
    loaded_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class CorrectionsContext(BaseModel):
    """Layer 3 context — recent corrections and session memory."""
    corrections: list[CorrectionEntry] = Field(default_factory=list)
    session_memory: dict[str, Any] = Field(default_factory=dict)


class ContextBundle(BaseModel):
    """All three context layers assembled for one session."""
    schema_ctx: SchemaContext
    domain_ctx: DomainContext
    corrections_ctx: CorrectionsContext


# ---------------------------------------------------------------------------
# Correction Engine
# ---------------------------------------------------------------------------

class FailureType(str, Enum):
    """Classification of an execution failure."""
    SYNTAX_ERROR = "SYNTAX_ERROR"
    JOIN_KEY_MISMATCH = "JOIN_KEY_MISMATCH"
    WRONG_DB_TYPE = "WRONG_DB_TYPE"
    DATA_QUALITY = "DATA_QUALITY"
    UNKNOWN = "UNKNOWN"


class JoinKeyMismatch(BaseModel):
    """Details of a detected join key format mismatch."""
    left_column: str
    right_column: str
    left_format: JoinKeyFormat
    right_format: JoinKeyFormat
    left_db: str
    right_db: str


class CorrectionResult(BaseModel):
    """Result of one CorrectionEngine.correct() call."""
    success: bool
    corrected_query: str | None = None
    corrected_plan: QueryPlan | None = None
    fix_strategy: str
    attempt_number: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class SessionMemory(BaseModel):
    """Memory loaded from agent/memory/ for a session."""
    successful_patterns: list[dict[str, Any]] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    query_corrections: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class DABQuery(BaseModel):
    """One query from the DataAgentBench benchmark."""
    id: str
    question: str
    expected_answer: Any
    category: str
    databases: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """Result from LLM-as-judge scorer."""
    passed: bool
    rationale: str
    confidence: float


class BenchmarkResult(BaseModel):
    """Aggregated result from a full benchmark run."""
    run_id: str
    timestamp: float
    agent_url: str
    n_trials: int
    total_queries: int
    pass_at_1: float
    per_query_scores: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class RegressionResult(BaseModel):
    """Result from running the regression suite."""
    passed: bool
    current_score: float
    previous_score: float
    delta: float
    failed_queries: list[str] = Field(default_factory=list)
