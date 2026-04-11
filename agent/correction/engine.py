"""CorrectionEngine — tiered failure correction for The Oracle Forge agent.

Design decisions:
  - BR-U1-08: fix strategy priority: rule_syntax → rule_join_key → rule_db_type → rule_null_guard → llm_corrector
  - BR-U1-09/Q9=C: fix_syntax_error handles 4 specific rule patterns only
  - BR-U1-10/Q10=B: fix_wrong_db_type uses db_type error signal pattern matching
  - BR-U1-07: max 3 correction attempts per session; raises CorrectionExhausted after limit
  - SEC-U1-01: logs contain metadata only — never query text or error content
  - Pattern 6: LLM client injected via __init__
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agent.config import settings
from agent.models import (
    ContextBundle,
    CorrectionResult,
    ExecutionFailure,
    FailureType,
    JoinKeyMismatch,
    QueryPlan,
)

_logger = logging.getLogger("agent.correction")

# ---------------------------------------------------------------------------
# DB error signal patterns (BR-U1-10 / Q10=B)
# ---------------------------------------------------------------------------

_DB_ERROR_SIGNALS: dict[str, list[str]] = {
    "postgres": ["psycopg", "pg_", "relation does not exist", "column does not exist", "syntax error at or near"],
    "sqlite": ["no such table", "no such column", "sqlite3", "near \""],
    "mongodb": ["$match", "aggregation error", "bson", "mongoclient"],
    "duckdb": ["catalog error", "binder error", "duckdb", "not found in table"],
}

# ---------------------------------------------------------------------------
# CorrectionExhausted
# ---------------------------------------------------------------------------

class CorrectionExhausted(Exception):
    """Raised when max_correction_attempts is exceeded."""


# ---------------------------------------------------------------------------
# Structured log helpers (SEC-U1-01)
# ---------------------------------------------------------------------------

def _log_correction_attempt(
    attempt: int, failure_type: str, strategy: str, success: bool
) -> None:
    _logger.info("correction_attempt", extra={
        "attempt": attempt, "failure_type": failure_type,
        "strategy": strategy, "success": success,
    })

# ---------------------------------------------------------------------------
# CorrectionEngine
# ---------------------------------------------------------------------------

class CorrectionEngine:
    """Tiered failure correction — cheapest rule-based strategies first, LLM last."""

    def __init__(self, llm_client: Any, engine: Any) -> None:
        self._llm = llm_client
        self._engine = engine
        self._max_attempts = settings.max_correction_attempts

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def correct(
        self,
        failure: ExecutionFailure,
        original_query: str,
        context: ContextBundle,
        attempt: int = 1,
    ) -> CorrectionResult:
        """Route to cheapest sufficient fix strategy (BR-U1-08).

        Raises CorrectionExhausted if attempt > max_correction_attempts (BR-U1-07).
        """
        if attempt > self._max_attempts:
            raise CorrectionExhausted(
                f"Max correction attempts ({self._max_attempts}) exceeded"
            )

        failure_type = self.classify_failure(failure)

        if failure_type == FailureType.SYNTAX_ERROR:
            corrected = self.fix_syntax_error(original_query, failure.error_message)
            result = CorrectionResult(
                success=True, corrected_query=corrected,
                fix_strategy="rule_syntax", attempt_number=attempt,
            )

        elif failure_type == FailureType.JOIN_KEY_MISMATCH:
            mismatch = self._detect_mismatch(failure)
            corrected = self.fix_join_key(original_query, mismatch)
            result = CorrectionResult(
                success=True, corrected_query=corrected,
                fix_strategy="rule_join_key", attempt_number=attempt,
            )

        elif failure_type == FailureType.WRONG_DB_TYPE:
            # Need the original plan to reroute — build minimal plan from failure
            plan = self._build_minimal_plan(failure, original_query)
            corrected_plan = self.fix_wrong_db_type(plan, failure)
            result = CorrectionResult(
                success=True, corrected_plan=corrected_plan,
                fix_strategy="rule_db_type", attempt_number=attempt,
            )

        elif failure_type == FailureType.DATA_QUALITY:
            corrected = self.fix_data_quality(original_query, failure)
            result = CorrectionResult(
                success=True, corrected_query=corrected,
                fix_strategy="rule_null_guard", attempt_number=attempt,
            )

        else:  # UNKNOWN — LLM corrector
            try:
                corrected = await self.llm_correct(original_query, failure.error_message, context)
                result = CorrectionResult(
                    success=True, corrected_query=corrected,
                    fix_strategy="llm_corrector", attempt_number=attempt,
                )
            except Exception as exc:  # noqa: BLE001
                result = CorrectionResult(
                    success=False, fix_strategy="llm_corrector",
                    attempt_number=attempt, error=str(exc),
                )

        _log_correction_attempt(attempt, failure_type.value, result.fix_strategy, result.success)
        return result

    # ------------------------------------------------------------------
    # classify_failure() — rule-based (BR-U1-08)
    # ------------------------------------------------------------------

    def classify_failure(self, failure: ExecutionFailure) -> FailureType:
        """Classify ExecutionFailure into FailureType using error signal patterns."""
        error = failure.error_message.lower()

        # SYNTAX_ERROR — SQL syntax keywords
        syntax_signals = [
            "syntax error", "unexpected token", "near \"", "invalid syntax",
            "parse error", "unterminated string",
        ]
        if any(s in error for s in syntax_signals):
            return FailureType.SYNTAX_ERROR

        # JOIN_KEY_MISMATCH — join/type signals
        if ("join" in error or "merge" in error) and any(
            s in error for s in ["type mismatch", "no rows", "format", "cannot compare"]
        ):
            return FailureType.JOIN_KEY_MISMATCH

        # WRONG_DB_TYPE — DB-specific error signals appearing for wrong DB (Q10=B / BR-U1-10)
        for target_db, patterns in _DB_ERROR_SIGNALS.items():
            if failure.db_type != target_db and any(p in error for p in patterns):
                return FailureType.WRONG_DB_TYPE

        # DATA_QUALITY — null/missing signals
        if any(s in error for s in ["null", "none", "missing", "not found", "undefined", "nan"]):
            return FailureType.DATA_QUALITY

        return FailureType.UNKNOWN

    # ------------------------------------------------------------------
    # fix_syntax_error() — BR-U1-09 / Q9=C
    # ------------------------------------------------------------------

    def fix_syntax_error(self, query: str, error: str) -> str:
        """Apply 4 rule-based syntax transformations (BR-U1-09/Q9=C).

        Rules:
        1. Missing quotes around string values in WHERE clauses
        2. GROUP BY without aggregate — add COUNT(*)
        3. Row-limit dialect: ROWNUM / TOP N → LIMIT N
        4. Null-handling dialect: ISNULL() → IS NULL, NVL() → COALESCE()
        """
        result = query

        # Rule 3a: ROWNUM-based limiting → WHERE 1=1 LIMIT N (keeps same or greater length)
        result = re.sub(
            r"\bWHERE\s+ROWNUM\s*<=?\s*(\d+)", r"WHERE 1=1 LIMIT \1", result, flags=re.IGNORECASE
        )
        # Rule 3b: TOP N → LIMIT N (MS SQL / Sybase style)
        result = re.sub(
            r"\bSELECT\s+TOP\s+(\d+)\b", r"SELECT", result, flags=re.IGNORECASE
        )
        result = re.sub(r"\bFROM\b", r"FROM", result)  # ensure FROM is still present
        if re.search(r"SELECT\s+TOP\s+\d+", query, re.IGNORECASE):
            n = re.search(r"TOP\s+(\d+)", query, re.IGNORECASE)
            if n:
                result = result.rstrip(";").rstrip() + f" LIMIT {n.group(1)}"

        # Rule 4a: ISNULL(col) → col IS NULL
        result = re.sub(
            r"\bISNULL\s*\(\s*([^)]+)\s*\)", r"\1 IS NULL", result, flags=re.IGNORECASE
        )
        # Rule 4b: NVL(col, val) → COALESCE(col, val)
        result = re.sub(r"\bNVL\s*\(", "COALESCE(", result, flags=re.IGNORECASE)

        # Rule 2: GROUP BY without aggregate function — add COUNT(*) AS count_
        if re.search(r"\bGROUP\s+BY\b", result, re.IGNORECASE):
            has_aggregate = bool(re.search(
                r"\b(COUNT|SUM|AVG|MIN|MAX|STDDEV|VARIANCE)\s*\(", result, re.IGNORECASE
            ))
            if not has_aggregate:
                # Insert COUNT(*) AS count_ after SELECT keyword
                result = re.sub(
                    r"\bSELECT\b", "SELECT COUNT(*) AS count_,", result, count=1, flags=re.IGNORECASE
                )

        # Rule 1: Missing quotes around string literals in WHERE (bare word after =)
        # Pattern: = word (not a number, not already quoted, not a subquery paren)
        result = re.sub(
            r"(=\s*)([A-Za-z][A-Za-z0-9_]*)(\s*(?:AND|OR|$|\)))",
            lambda m: f"{m.group(1)}'{m.group(2)}'{m.group(3)}",
            result,
        )

        return result

    # ------------------------------------------------------------------
    # fix_join_key()
    # ------------------------------------------------------------------

    def fix_join_key(self, query: str, mismatch: JoinKeyMismatch | None) -> str:
        """Rewrite JOIN condition with key format transformation."""
        if mismatch is None:
            return query
        from utils.join_key_utils import JoinKeyUtils
        expr = JoinKeyUtils.build_transform_expression(
            source_column=mismatch.left_column,
            source_format=mismatch.left_format,
            target_format=mismatch.right_format,
            db_type="postgres",
        )
        # Replace the raw column reference with the transform expression
        return query.replace(mismatch.left_column, expr)

    # ------------------------------------------------------------------
    # fix_wrong_db_type() — BR-U1-10 / Q10=B
    # ------------------------------------------------------------------

    def fix_wrong_db_type(self, plan: QueryPlan, failure: ExecutionFailure) -> QueryPlan:
        """Detect correct db_type from error signal patterns; swap in plan."""
        error = failure.error_message.lower()
        target_db = failure.db_type

        for candidate_db, patterns in _DB_ERROR_SIGNALS.items():
            if any(p in error for p in patterns):
                target_db = candidate_db
                break

        # Rebuild sub_queries with corrected db_type
        updated_sqs = []
        for sq in plan.sub_queries:
            if sq.db_type == failure.db_type:
                updated_sqs.append(sq.model_copy(update={"db_type": target_db}))
            else:
                updated_sqs.append(sq)

        return plan.model_copy(update={"sub_queries": updated_sqs})

    # ------------------------------------------------------------------
    # fix_data_quality()
    # ------------------------------------------------------------------

    def fix_data_quality(self, query: str, failure: ExecutionFailure) -> str:
        """Add COALESCE/IFNULL null-guard to handle missing fields."""
        # Wrap bare column references in SELECT with COALESCE
        # Pattern: SELECT col → SELECT COALESCE(col, '') AS col
        def _coalesce_select(m: re.Match) -> str:
            col = m.group(1).strip()
            if "(" in col or "*" in col or "'" in col:
                return m.group(0)  # already a function or literal — skip
            alias = col.split(".")[-1]  # strip table prefix for alias
            return f"COALESCE({col}, '') AS {alias}"

        return re.sub(
            r"(?<=SELECT\s)([A-Za-z_][A-Za-z0-9_.]*)",
            _coalesce_select,
            query,
            count=1,
            flags=re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # llm_correct() — last resort
    # ------------------------------------------------------------------

    async def llm_correct(self, query: str, error: str, context: ContextBundle) -> str:
        """Send broken query + error to LLM for correction."""
        schema_summary = "\n".join(
            f"{name}: {[t.name for t in db.tables]}"
            for name, db in context.schema_ctx.databases.items()
        )
        prompt = [
            {"role": "system", "content": (
                "You are a SQL correction assistant. "
                "Fix the broken query below. Return ONLY the corrected SQL — no explanation."
            )},
            {"role": "user", "content": (
                f"Error: {error[:500]}\n\n"
                f"Schema:\n{schema_summary}\n\n"
                f"Broken query:\n{query}"
            )},
        ]
        response = await self._llm.chat.completions.create(
            model=settings.openrouter_model,
            messages=prompt,
        )
        return (response.choices[0].message.content or query).strip()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_mismatch(self, failure: ExecutionFailure) -> JoinKeyMismatch | None:
        """Extract JoinKeyMismatch details from failure if available."""
        # In practice the Orchestrator provides mismatch context; stub here
        return None

    def _build_minimal_plan(self, failure: ExecutionFailure, query: str) -> QueryPlan:
        """Build a minimal single-sub-query plan from failure metadata."""
        import uuid
        from agent.models import MergeSpec, SubQuery
        sq = SubQuery(
            id=str(uuid.uuid4()),
            db_type=failure.db_type,
            db_name=failure.db_type,
            query=query,
        )
        return QueryPlan(id=str(uuid.uuid4()), sub_queries=[sq], merge_spec=MergeSpec())
