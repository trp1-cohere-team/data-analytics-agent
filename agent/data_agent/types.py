"""Shared dataclasses for the OracleForge Data Agent.

All domain entities used across the agent live here. Zero side effects on import.
FR-01, FR-02, FR-04, FR-05, FR-06, FR-12.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Valid domain constants
# ---------------------------------------------------------------------------

VALID_FAILURE_CATEGORIES = frozenset({"query", "join-key", "db-type", "data-quality"})
VALID_STEP_STATUSES = frozenset({"pending", "success", "failed", "corrected"})
VALID_MEMORY_ROLES = frozenset({"user", "assistant"})

# ---------------------------------------------------------------------------
# FR-01: Agent Facade return type
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Single return type from ``run_agent()``."""

    answer: str
    confidence: float
    trace_id: str
    tool_calls: list[dict] = field(default_factory=list)
    failure_count: int = 0

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.failure_count < 0:
            raise ValueError(f"failure_count must be >= 0, got {self.failure_count}")


# ---------------------------------------------------------------------------
# FR-06: Append-only event ledger entry
# ---------------------------------------------------------------------------


@dataclass
class TraceEvent:
    """Structured JSONL event for the append-only event ledger."""

    event_type: str
    session_id: str
    timestamp: str
    tool_name: str = ""
    db_type: str = ""
    input_summary: str = ""
    outcome: str = ""
    diagnosis: str = ""
    retry_count: int = 0
    backend: str = ""
    extra: dict = field(default_factory=dict)

    # -- serialization (PBT-02 round-trip) ----------------------------------

    def to_dict(self) -> dict:
        """Serialize to dict, omitting fields that hold their default value.

        Only ``event_type``, ``session_id``, and ``timestamp`` are always
        present (identity fields).  All optional fields are included only
        when they carry meaningful data, keeping JSONL lines compact and
        readable.
        """
        d: dict = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.db_type:
            d["db_type"] = self.db_type
        if self.input_summary:
            d["input_summary"] = self.input_summary
        if self.outcome:
            d["outcome"] = self.outcome
        if self.diagnosis:
            d["diagnosis"] = self.diagnosis
        if self.retry_count:
            d["retry_count"] = self.retry_count
        if self.backend:
            d["backend"] = self.backend
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TraceEvent":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# FR-02: 6-layer context packet
# ---------------------------------------------------------------------------


@dataclass
class ContextPacket:
    """6-layer context composition.  Precedence: Layer 6 (highest) → Layer 1 (lowest)."""

    table_usage: str = ""            # Layer 1
    human_annotations: str = ""      # Layer 2
    institutional_knowledge: str = ""  # Layer 3
    runtime_context: dict = field(default_factory=dict)  # Layer 4
    interaction_memory: str = ""     # Layer 5
    user_question: str = ""          # Layer 6

    # -- backward-compat aliases (FR-02) ------------------------------------

    @property
    def schema_and_metadata(self) -> str:
        return self.table_usage

    @property
    def institutional_and_domain(self) -> str:
        parts = [p for p in (self.human_annotations, self.institutional_knowledge) if p]
        return "\n\n".join(parts)

    # -- serialization (PBT-02 round-trip) ----------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContextPacket":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# FR-04: Execution plan step
# ---------------------------------------------------------------------------


@dataclass
class ExecutionStep:
    """Single step in a multi-step execution plan."""

    step_number: int
    action: str
    tool_name: str = ""
    parameters: dict = field(default_factory=dict)
    expected_outcome: str = ""
    status: str = "pending"

    def __post_init__(self) -> None:
        if self.status not in VALID_STEP_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STEP_STATUSES}, got '{self.status}'"
            )


# ---------------------------------------------------------------------------
# FR-04: Correction log entry
# ---------------------------------------------------------------------------


@dataclass
class CorrectionEntry:
    """Structured entry for ``kb/corrections/corrections_log.md``."""

    timestamp: str
    session_id: str
    original_error: str
    diagnosis_category: str
    correction_applied: str
    retry_number: int
    outcome: str

    def __post_init__(self) -> None:
        if self.diagnosis_category not in VALID_FAILURE_CATEGORIES:
            raise ValueError(
                f"diagnosis_category must be one of {VALID_FAILURE_CATEGORIES}, "
                f"got '{self.diagnosis_category}'"
            )


# ---------------------------------------------------------------------------
# FR-02 support: individual layer data
# ---------------------------------------------------------------------------


@dataclass
class LayerContent:
    """Individual layer data before composition into ContextPacket."""

    layer_number: int
    layer_name: str
    content: str
    precedence: int = 0

    def __post_init__(self) -> None:
        if self.precedence == 0:
            self.precedence = self.layer_number


# ---------------------------------------------------------------------------
# FR-04 support: failure diagnosis output
# ---------------------------------------------------------------------------


@dataclass
class FailureDiagnosis:
    """Output of ``failure_diagnostics.classify()``."""

    category: str
    explanation: str
    suggested_fix: str = ""
    original_error: str = ""

    def __post_init__(self) -> None:
        if self.category not in VALID_FAILURE_CATEGORIES:
            raise ValueError(
                f"category must be one of {VALID_FAILURE_CATEGORIES}, "
                f"got '{self.category}'"
            )


# ---------------------------------------------------------------------------
# FR-03 support: tool descriptor from tools.yaml
# ---------------------------------------------------------------------------


@dataclass
class ToolDescriptor:
    """Describes a single MCP tool from the unified registry."""

    name: str
    kind: str
    source: str
    description: str
    parameters: dict = field(default_factory=dict)
    schema_summary: str = ""


# ---------------------------------------------------------------------------
# FR-03 support: unified invocation result
# ---------------------------------------------------------------------------


@dataclass
class InvokeResult:
    """Unified result from any tool invocation (MCP Toolbox or DuckDB bridge)."""

    success: bool
    tool_name: str
    result: Any = None
    error: str = ""
    error_type: str = ""
    db_type: str = ""


# ---------------------------------------------------------------------------
# FR-05 support: memory turn
# ---------------------------------------------------------------------------


@dataclass
class MemoryTurn:
    """Single turn in the session transcript (``.jsonl``)."""

    role: str
    content: str
    timestamp: str
    session_id: str

    def __post_init__(self) -> None:
        if self.role not in VALID_MEMORY_ROLES:
            raise ValueError(
                f"role must be one of {VALID_MEMORY_ROLES}, got '{self.role}'"
            )
