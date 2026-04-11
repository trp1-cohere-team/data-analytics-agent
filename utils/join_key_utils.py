"""JoinKeyUtils — cross-database join key format detection and transformation.

All functions are pure (no side effects, no I/O, no global state mutation).
Same inputs always produce same outputs.
"""
from __future__ import annotations

import re
from typing import Any

from agent.models import JoinKeyFormat, JoinKeyFormatResult

# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level constants — compiled once at import)
# ---------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"^\d+$")
_PREFIXED_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# ---------------------------------------------------------------------------
# Unsupported transformation pairs — return None, never raise
# ---------------------------------------------------------------------------

_UNSUPPORTED_TRANSFORMS: frozenset[tuple[JoinKeyFormat, JoinKeyFormat]] = frozenset(
    {
        (JoinKeyFormat.INTEGER, JoinKeyFormat.UUID),
        (JoinKeyFormat.UUID, JoinKeyFormat.INTEGER),
        (JoinKeyFormat.UUID, JoinKeyFormat.PREFIXED_STRING),
        (JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.UUID),
        (JoinKeyFormat.COMPOSITE, JoinKeyFormat.INTEGER),
        (JoinKeyFormat.COMPOSITE, JoinKeyFormat.PREFIXED_STRING),
        (JoinKeyFormat.COMPOSITE, JoinKeyFormat.UUID),
        (JoinKeyFormat.INTEGER, JoinKeyFormat.COMPOSITE),
        (JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.COMPOSITE),
        (JoinKeyFormat.UNKNOWN, JoinKeyFormat.INTEGER),
        (JoinKeyFormat.UNKNOWN, JoinKeyFormat.PREFIXED_STRING),
        (JoinKeyFormat.UNKNOWN, JoinKeyFormat.UUID),
        (JoinKeyFormat.UNKNOWN, JoinKeyFormat.COMPOSITE),
    }
)

# Format precedence for tie-breaking: higher index = higher precedence
_PRECEDENCE: dict[JoinKeyFormat, int] = {
    JoinKeyFormat.UNKNOWN: 0,
    JoinKeyFormat.INTEGER: 1,
    JoinKeyFormat.COMPOSITE: 2,
    JoinKeyFormat.PREFIXED_STRING: 3,
    JoinKeyFormat.UUID: 4,
}


# ---------------------------------------------------------------------------
# Internal: single-value classifier
# ---------------------------------------------------------------------------

def _classify_single(value: Any) -> JoinKeyFormat:
    """Classify one key value into a JoinKeyFormat.

    Decision tree per domain-entities.md FormatClassifier specification.
    """
    if isinstance(value, int):
        return JoinKeyFormat.INTEGER
    if isinstance(value, (list, tuple)):
        return JoinKeyFormat.COMPOSITE
    if isinstance(value, str):
        if _DIGITS_RE.match(value):
            return JoinKeyFormat.INTEGER
        if _PREFIXED_RE.match(value):
            return JoinKeyFormat.PREFIXED_STRING
        if _UUID_RE.match(value):
            return JoinKeyFormat.UUID
        if "|" in value or "::" in value:
            return JoinKeyFormat.COMPOSITE
    return JoinKeyFormat.UNKNOWN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_format(key_samples: list[Any]) -> JoinKeyFormatResult:
    """Detect the key format from a list of sample values.

    Single-sample: classifies directly, secondary_formats=[].
    Multi-sample: votes across all samples; primary = majority format
    (ties broken by precedence); secondary = minority formats (UNKNOWN excluded).

    Rules:
    - Empty list → UNKNOWN primary, [] secondary (JKU-01)
    - Single element → direct classify, no voting (JKU-02)
    - UNKNOWN never appears in secondary_formats (JKU-04)
    """
    if not key_samples:
        return JoinKeyFormatResult(primary_format=JoinKeyFormat.UNKNOWN, secondary_formats=[])

    if len(key_samples) == 1:
        return JoinKeyFormatResult(
            primary_format=_classify_single(key_samples[0]),
            secondary_formats=[],
        )

    # Multi-sample voting
    from collections import Counter
    counts: Counter[JoinKeyFormat] = Counter(_classify_single(s) for s in key_samples)
    counts.pop(JoinKeyFormat.UNKNOWN, None)  # UNKNOWN never wins primary (JKU-03 precedence)

    if not counts:
        return JoinKeyFormatResult(primary_format=JoinKeyFormat.UNKNOWN, secondary_formats=[])

    max_count = max(counts.values())
    candidates = [fmt for fmt, cnt in counts.items() if cnt == max_count]
    primary = max(candidates, key=lambda f: _PRECEDENCE[f])  # JKU-03: precedence on ties

    secondary = [fmt for fmt in counts if fmt != primary]  # JKU-04: no UNKNOWN in secondary
    return JoinKeyFormatResult(primary_format=primary, secondary_formats=secondary)


def transform_key(
    value: Any,
    source_fmt: JoinKeyFormat,
    target_fmt: JoinKeyFormat,
    *,
    prefix: str | None = None,
    width: int | None = None,
) -> Any:
    """Transform a key value from source format to target format.

    Returns None for unsupported pairs (JKU-05) — never raises.
    Returns value unchanged for identity transforms (source == target).

    Args:
        value: The key value to transform.
        source_fmt: Detected format of the value.
        target_fmt: Required format for the join.
        prefix: Required when target is PREFIXED_STRING (e.g. "CUST").
        width: Zero-padding width for PREFIXED_STRING digits.
    """
    # NullReturnGuard: unsupported pairs
    if (source_fmt, target_fmt) in _UNSUPPORTED_TRANSFORMS:
        return None

    # PREFIXED_STRING → PREFIXED_STRING (re-pad) — must run before identity check
    if source_fmt == JoinKeyFormat.PREFIXED_STRING and target_fmt == JoinKeyFormat.PREFIXED_STRING:
        if isinstance(value, str) and "-" in value:
            pfx, digits = value.rsplit("-", 1)
            try:
                n = int(digits)
                pad = str(n).zfill(width) if width else digits
                return f"{pfx}-{pad}"
            except ValueError:
                return None
        return None

    # Identity
    if source_fmt == target_fmt:
        return value

    # PREFIXED_STRING → INTEGER: strip prefix, parse digits
    if source_fmt == JoinKeyFormat.PREFIXED_STRING and target_fmt == JoinKeyFormat.INTEGER:
        if isinstance(value, str) and "-" in value:
            digit_part = value.rsplit("-", 1)[-1]
            try:
                return int(digit_part)
            except ValueError:
                return None
        return None

    # INTEGER → PREFIXED_STRING: requires prefix
    if source_fmt == JoinKeyFormat.INTEGER and target_fmt == JoinKeyFormat.PREFIXED_STRING:
        if prefix is None:
            return None  # JKU-06: cannot build without prefix
        n = int(value)
        pad = str(n).zfill(width) if width else str(n)
        return f"{prefix}-{pad}"

    # PREFIXED_STRING → PREFIXED_STRING: re-pad digits
    if source_fmt == JoinKeyFormat.PREFIXED_STRING and target_fmt == JoinKeyFormat.PREFIXED_STRING:
        if isinstance(value, str) and "-" in value:
            pfx, digits = value.rsplit("-", 1)
            try:
                n = int(digits)
                pad = str(n).zfill(width) if width else digits
                return f"{pfx}-{pad}"
            except ValueError:
                return None
        return None

    return None  # fallback for any unhandled pair


def build_transform_expression(
    source_column: str,
    source_fmt: JoinKeyFormat,
    target_fmt: JoinKeyFormat,
    db_type: str,
    *,
    prefix: str | None = None,
    width: int | None = None,
) -> str | None:
    """Build a SQL/MQL expression that transforms the join key in-query.

    Returns None if the pair is unsupported or parameters cannot be resolved (JKU-06).
    The returned expression contains no unresolved {placeholder} syntax.

    Args:
        source_column: Column reference in the query (e.g. "customer_id").
        source_fmt: Format of the source column.
        target_fmt: Required target format.
        db_type: Database dialect: "postgres" | "sqlite" | "duckdb" | "mongodb".
        prefix: Prefix string for PREFIXED_STRING target (e.g. "CUST").
        width: Zero-padding width for digit part.
    """
    if (source_fmt, target_fmt) in _UNSUPPORTED_TRANSFORMS:
        return None

    col = source_column
    w = width or 5  # default zero-padding width

    # PREFIXED_STRING → PREFIXED_STRING (re-pad) — must run before identity check
    if source_fmt == JoinKeyFormat.PREFIXED_STRING and target_fmt == JoinKeyFormat.PREFIXED_STRING:
        if db_type in ("postgres", "duckdb"):
            return (
                f"CONCAT(SPLIT_PART({col}, '-', 1), '-', "
                f"LPAD(CAST(SPLIT_PART({col}, '-', 2) AS TEXT), {w}, '0'))"
            )
        if db_type == "sqlite":
            return (
                f"SUBSTR({col}, 1, INSTR({col}, '-')) || "
                f"printf('%0{w}d', CAST(SUBSTR({col}, INSTR({col}, '-') + 1) AS INTEGER))"
            )
        return None  # mongodb not supported

    if source_fmt == target_fmt:
        return source_column  # identity — no transformation needed

    # PREFIXED_STRING → INTEGER
    if source_fmt == JoinKeyFormat.PREFIXED_STRING and target_fmt == JoinKeyFormat.INTEGER:
        if db_type in ("postgres", "duckdb"):
            return f"CAST(REGEXP_REPLACE({col}, '^[A-Z]+-', '') AS INTEGER)"
        if db_type == "sqlite":
            return f"CAST(SUBSTR({col}, INSTR({col}, '-') + 1) AS INTEGER)"
        if db_type == "mongodb":
            return f"{{$toInt: {{$arrayElemAt: [{{$split: ['${col}', '-']}}, -1]}}}}"
        return None

    # INTEGER → PREFIXED_STRING
    if source_fmt == JoinKeyFormat.INTEGER and target_fmt == JoinKeyFormat.PREFIXED_STRING:
        if prefix is None:
            return None  # JKU-06: cannot resolve prefix
        if db_type in ("postgres", "duckdb"):
            return f"CONCAT('{prefix}-', LPAD(CAST({col} AS TEXT), {w}, '0'))"
        if db_type == "sqlite":
            return f"'{prefix}-' || printf('%0{w}d', {col})"
        if db_type == "mongodb":
            return f"{{$concat: ['{prefix}-', {{$substr: [{{$toString: '${col}'}}, 0, -1]}}]}}"
        return None

    return None
