"""Unit tests for utils/join_key_utils.py.

Covers:
- _classify_single: all 5 format paths + UNKNOWN + edge cases
- detect_format: empty / single / multi-sample / voting / tie-breaking
- transform_key: all supported pairs + unsupported=None + identity
- build_transform_expression: all 4 dialects + None on unsupported
- PBT-U5-01: round-trip INTEGER ↔ PREFIXED_STRING
- PBT-U5-02: output constraint (result always a JoinKeyFormatResult)
- PBT-U5-03: idempotency (same samples → same result)
- PBT-U5-04: monotonicity (majority format wins)
- PBT-U5-05: expression validity (no unresolved placeholders)
"""
from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings as h_settings

from agent.models import JoinKeyFormat, JoinKeyFormatResult
from tests.unit.strategies import (
    INVARIANT_SETTINGS,
    integer_keys,
    key_samples_with_majority,
    prefixed_keys,
    uuid_keys,
    validate_sql_expression,
)
from utils.join_key_utils import (
    _classify_single,
    _UNSUPPORTED_TRANSFORMS,
    build_transform_expression,
    detect_format,
    transform_key,
)


# ===========================================================================
# _classify_single
# ===========================================================================

class TestClassifySingle:
    def test_int_type_returns_integer(self):
        assert _classify_single(42) == JoinKeyFormat.INTEGER
        assert _classify_single(0) == JoinKeyFormat.INTEGER
        assert _classify_single(999_999) == JoinKeyFormat.INTEGER

    def test_digit_string_returns_integer(self):
        assert _classify_single("1234") == JoinKeyFormat.INTEGER
        assert _classify_single("0") == JoinKeyFormat.INTEGER
        assert _classify_single("000123") == JoinKeyFormat.INTEGER

    def test_prefixed_string_format(self):
        assert _classify_single("CUST-01234") == JoinKeyFormat.PREFIXED_STRING
        assert _classify_single("ORD-007") == JoinKeyFormat.PREFIXED_STRING
        assert _classify_single("ITEM-00001") == JoinKeyFormat.PREFIXED_STRING
        assert _classify_single("A-1") == JoinKeyFormat.PREFIXED_STRING

    def test_uuid_format(self):
        sample = str(uuid.uuid4())
        assert _classify_single(sample) == JoinKeyFormat.UUID

    def test_uuid_uppercase_accepted(self):
        upper = str(uuid.uuid4()).upper()
        assert _classify_single(upper) == JoinKeyFormat.UUID

    def test_list_returns_composite(self):
        assert _classify_single([1, 2]) == JoinKeyFormat.COMPOSITE
        assert _classify_single(["a", "b"]) == JoinKeyFormat.COMPOSITE

    def test_tuple_returns_composite(self):
        assert _classify_single((1, "X")) == JoinKeyFormat.COMPOSITE

    def test_pipe_separator_composite(self):
        assert _classify_single("A|B") == JoinKeyFormat.COMPOSITE

    def test_double_colon_composite(self):
        assert _classify_single("A::B") == JoinKeyFormat.COMPOSITE

    def test_none_returns_unknown(self):
        assert _classify_single(None) == JoinKeyFormat.UNKNOWN

    def test_float_returns_unknown(self):
        assert _classify_single(3.14) == JoinKeyFormat.UNKNOWN

    def test_arbitrary_string_returns_unknown(self):
        assert _classify_single("hello world") == JoinKeyFormat.UNKNOWN
        assert _classify_single("") == JoinKeyFormat.UNKNOWN
        assert _classify_single("cust-123") == JoinKeyFormat.UNKNOWN  # lowercase prefix


# ===========================================================================
# detect_format
# ===========================================================================

class TestDetectFormat:
    def test_empty_list_returns_unknown(self):
        result = detect_format([])
        assert result.primary_format == JoinKeyFormat.UNKNOWN
        assert result.secondary_formats == []

    def test_single_integer_value(self):
        result = detect_format([42])
        assert result.primary_format == JoinKeyFormat.INTEGER
        assert result.secondary_formats == []

    def test_single_prefixed_string(self):
        result = detect_format(["CUST-00042"])
        assert result.primary_format == JoinKeyFormat.PREFIXED_STRING
        assert result.secondary_formats == []

    def test_single_uuid(self):
        result = detect_format([str(uuid.uuid4())])
        assert result.primary_format == JoinKeyFormat.UUID
        assert result.secondary_formats == []

    def test_majority_wins(self):
        samples = [1, 2, 3, "CUST-001", "CUST-002"]
        result = detect_format(samples)
        assert result.primary_format == JoinKeyFormat.INTEGER

    def test_minority_in_secondary(self):
        samples = [1, 2, 3, "CUST-001"]
        result = detect_format(samples)
        assert result.primary_format == JoinKeyFormat.INTEGER
        assert JoinKeyFormat.PREFIXED_STRING in result.secondary_formats

    def test_unknown_excluded_from_secondary(self):
        samples = [1, 2, 3, None, "garbage"]
        result = detect_format(samples)
        assert JoinKeyFormat.UNKNOWN not in result.secondary_formats

    def test_all_unknown_returns_unknown(self):
        result = detect_format([None, 3.14, "garbage"])
        assert result.primary_format == JoinKeyFormat.UNKNOWN
        assert result.secondary_formats == []

    def test_tie_broken_by_precedence(self):
        # UUID has higher precedence than PREFIXED_STRING
        uid = str(uuid.uuid4())
        samples = [uid, uid, "CUST-001", "CUST-002"]
        result = detect_format(samples)
        assert result.primary_format == JoinKeyFormat.UUID

    def test_returns_joinkey_format_result_instance(self):
        result = detect_format([1, 2])
        assert isinstance(result, JoinKeyFormatResult)


# ===========================================================================
# transform_key
# ===========================================================================

class TestTransformKey:
    # --- Identity ---
    def test_identity_integer(self):
        assert transform_key(42, JoinKeyFormat.INTEGER, JoinKeyFormat.INTEGER) == 42

    def test_identity_prefixed_string(self):
        val = "CUST-00042"
        assert transform_key(val, JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, width=5) == "CUST-00042"

    def test_identity_uuid(self):
        val = str(uuid.uuid4())
        assert transform_key(val, JoinKeyFormat.UUID, JoinKeyFormat.UUID) == val

    # --- INTEGER → PREFIXED_STRING ---
    def test_integer_to_prefixed_with_prefix_and_width(self):
        result = transform_key(42, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, prefix="CUST", width=5)
        assert result == "CUST-00042"

    def test_integer_to_prefixed_no_prefix_returns_none(self):
        result = transform_key(42, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING)
        assert result is None

    def test_integer_to_prefixed_no_width_no_padding(self):
        result = transform_key(7, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, prefix="ORD")
        assert result == "ORD-7"

    # --- PREFIXED_STRING → INTEGER ---
    def test_prefixed_to_integer(self):
        result = transform_key("CUST-00042", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER)
        assert result == 42

    def test_prefixed_to_integer_leading_zeros_stripped(self):
        result = transform_key("ORD-007", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER)
        assert result == 7

    # --- PREFIXED_STRING → PREFIXED_STRING (re-pad) ---
    def test_prefixed_repad_wider(self):
        result = transform_key("ORD-007", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, width=5)
        assert result == "ORD-00007"

    def test_prefixed_repad_narrower(self):
        result = transform_key("ORD-00007", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, width=3)
        assert result == "ORD-007"

    # --- Unsupported pairs return None ---
    @pytest.mark.parametrize("src,tgt", list(_UNSUPPORTED_TRANSFORMS))
    def test_unsupported_returns_none(self, src, tgt):
        value: Any = 1 if src == JoinKeyFormat.INTEGER else "CUST-001"
        result = transform_key(value, src, tgt)
        assert result is None


# ===========================================================================
# build_transform_expression
# ===========================================================================

class TestBuildTransformExpression:
    # --- Identity ---
    def test_identity_returns_column_name(self):
        result = build_transform_expression("customer_id", JoinKeyFormat.INTEGER, JoinKeyFormat.INTEGER, "postgres")
        assert result == "customer_id"

    # --- Unsupported pairs ---
    @pytest.mark.parametrize("src,tgt", list(_UNSUPPORTED_TRANSFORMS))
    def test_unsupported_returns_none(self, src, tgt):
        result = build_transform_expression("col", src, tgt, "postgres")
        assert result is None

    # --- PREFIXED_STRING → INTEGER ---
    def test_prefixed_to_int_postgres(self):
        expr = build_transform_expression("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "postgres")
        assert expr is not None
        assert "REGEXP_REPLACE" in expr
        assert "cid" in expr

    def test_prefixed_to_int_sqlite(self):
        expr = build_transform_expression("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "sqlite")
        assert expr is not None
        assert "INSTR" in expr or "SUBSTR" in expr
        assert "cid" in expr

    def test_prefixed_to_int_duckdb(self):
        expr = build_transform_expression("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "duckdb")
        assert expr is not None
        assert "REGEXP_REPLACE" in expr

    def test_prefixed_to_int_mongodb(self):
        expr = build_transform_expression("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "mongodb")
        assert expr is not None
        assert "$toInt" in expr or "$split" in expr

    # --- INTEGER → PREFIXED_STRING ---
    def test_int_to_prefixed_postgres(self):
        expr = build_transform_expression("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "postgres", prefix="CUST", width=5)
        assert expr is not None
        assert "LPAD" in expr
        assert "CUST" in expr
        assert "cid" in expr

    def test_int_to_prefixed_sqlite(self):
        expr = build_transform_expression("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "sqlite", prefix="CUST", width=5)
        assert expr is not None
        assert "printf" in expr
        assert "CUST" in expr

    def test_int_to_prefixed_duckdb(self):
        expr = build_transform_expression("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "duckdb", prefix="ORD", width=5)
        assert expr is not None
        assert "LPAD" in expr

    def test_int_to_prefixed_no_prefix_returns_none(self):
        expr = build_transform_expression("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "postgres")
        assert expr is None

    # --- PREFIXED_STRING → PREFIXED_STRING ---
    def test_prefixed_repad_postgres(self):
        expr = build_transform_expression("oid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, "postgres", width=5)
        assert expr is not None
        assert "LPAD" in expr
        assert "oid" in expr

    def test_prefixed_repad_sqlite(self):
        expr = build_transform_expression("oid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, "sqlite", width=5)
        assert expr is not None
        assert "printf" in expr

    def test_prefixed_repad_mongodb_returns_none(self):
        # MongoDB re-pad not implemented
        expr = build_transform_expression("oid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, "mongodb", width=5)
        assert expr is None

    # --- No unresolved placeholders ---
    def test_no_unresolved_placeholders_in_any_expression(self):
        cases = [
            ("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "postgres", {}, ),
            ("cid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER, "sqlite", {}),
            ("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "postgres", {"prefix": "CUST", "width": 5}),
            ("cid", JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, "sqlite", {"prefix": "CUST", "width": 5}),
            ("oid", JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.PREFIXED_STRING, "postgres", {"width": 5}),
        ]
        for col, src, tgt, db, kwargs in cases:
            expr = build_transform_expression(col, src, tgt, db, **kwargs)
            if expr is not None:
                assert "{" not in expr and "}" not in expr, f"Unresolved placeholder in: {expr}"


# ===========================================================================
# Property-based tests (PBT-U5-01 through PBT-U5-05)
# ===========================================================================

class TestPBTJoinKeyUtils:
    # --- PBT-U5-01: Round-trip INTEGER ↔ PREFIXED_STRING ---
    @given(n=integer_keys(), prefix=prefixed_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-01"])
    def test_pbt_u5_01_round_trip(self, n: int, prefix: str) -> None:
        """transform INTEGER → PREFIXED_STRING → INTEGER returns original value."""
        # Extract prefix part from the generated prefixed key (use fixed prefix for clarity)
        pfx = "CUST"
        w = 5
        # INTEGER → PREFIXED_STRING
        intermediate = transform_key(n, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, prefix=pfx, width=w)
        assert intermediate is not None, f"First leg failed for n={n}"
        # PREFIXED_STRING → INTEGER
        recovered = transform_key(intermediate, JoinKeyFormat.PREFIXED_STRING, JoinKeyFormat.INTEGER)
        assert recovered == n, f"Round-trip failed: {n} → {intermediate} → {recovered}"

    # --- PBT-U5-02: Output constraint — detect_format always returns JoinKeyFormatResult ---
    @given(key=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-02"])
    def test_pbt_u5_02_output_constraint_integer(self, key: int) -> None:
        """detect_format on any single integer key always yields INTEGER primary."""
        result = detect_format([key])
        assert isinstance(result, JoinKeyFormatResult)
        assert result.primary_format == JoinKeyFormat.INTEGER
        assert result.secondary_formats == []

    @given(key=prefixed_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-02"])
    def test_pbt_u5_02_output_constraint_prefixed(self, key: str) -> None:
        """detect_format on any single prefixed key always yields PREFIXED_STRING primary."""
        result = detect_format([key])
        assert isinstance(result, JoinKeyFormatResult)
        assert result.primary_format == JoinKeyFormat.PREFIXED_STRING
        assert result.secondary_formats == []

    @given(key=uuid_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-02"])
    def test_pbt_u5_02_output_constraint_uuid(self, key: str) -> None:
        """detect_format on any single UUID key always yields UUID primary."""
        result = detect_format([key])
        assert isinstance(result, JoinKeyFormatResult)
        assert result.primary_format == JoinKeyFormat.UUID
        assert result.secondary_formats == []

    # --- PBT-U5-03: Idempotency — same inputs → same outputs ---
    @given(key=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-03"])
    def test_pbt_u5_03_idempotency_detect(self, key: int) -> None:
        """detect_format is deterministic: calling it twice returns identical results."""
        samples = [key, key + 1, key + 2]
        result1 = detect_format(samples)
        result2 = detect_format(samples)
        assert result1.primary_format == result2.primary_format
        assert set(result1.secondary_formats) == set(result2.secondary_formats)

    @given(n=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-03"])
    def test_pbt_u5_03_idempotency_transform(self, n: int) -> None:
        """transform_key is deterministic: same call returns identical result."""
        r1 = transform_key(n, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, prefix="ORD", width=5)
        r2 = transform_key(n, JoinKeyFormat.INTEGER, JoinKeyFormat.PREFIXED_STRING, prefix="ORD", width=5)
        assert r1 == r2

    # --- PBT-U5-04: Monotonicity — majority format wins ---
    @given(samples=key_samples_with_majority(JoinKeyFormat.INTEGER))
    @h_settings(INVARIANT_SETTINGS["PBT-U5-04"])
    def test_pbt_u5_04_majority_integer_wins(self, samples: list) -> None:
        """When INTEGER values are strict majority, primary_format == INTEGER."""
        result = detect_format(samples)
        assert result.primary_format == JoinKeyFormat.INTEGER

    @given(samples=key_samples_with_majority(JoinKeyFormat.PREFIXED_STRING))
    @h_settings(INVARIANT_SETTINGS["PBT-U5-04"])
    def test_pbt_u5_04_majority_prefixed_wins(self, samples: list) -> None:
        """When PREFIXED_STRING values are strict majority, primary_format == PREFIXED_STRING."""
        result = detect_format(samples)
        assert result.primary_format == JoinKeyFormat.PREFIXED_STRING

    # --- PBT-U5-05: Expression validity — no unresolved placeholders ---
    @given(n=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-05"])
    def test_pbt_u5_05_expression_validity_int_to_prefixed_postgres(self, n: int) -> None:
        """build_transform_expression for INTEGER→PREFIXED/postgres has no {} placeholders."""
        expr = build_transform_expression(
            "customer_id",
            JoinKeyFormat.INTEGER,
            JoinKeyFormat.PREFIXED_STRING,
            "postgres",
            prefix="CUST",
            width=5,
        )
        assert expr is not None
        validate_sql_expression(expr, "customer_id", "postgres")

    @given(key=prefixed_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-05"])
    def test_pbt_u5_05_expression_validity_prefixed_to_int_sqlite(self, key: str) -> None:
        """build_transform_expression for PREFIXED_STRING→INTEGER/sqlite has no {} placeholders."""
        expr = build_transform_expression(
            "product_id",
            JoinKeyFormat.PREFIXED_STRING,
            JoinKeyFormat.INTEGER,
            "sqlite",
        )
        assert expr is not None
        validate_sql_expression(expr, "product_id", "sqlite")

    @given(n=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-05"])
    def test_pbt_u5_05_expression_validity_int_to_prefixed_sqlite(self, n: int) -> None:
        """build_transform_expression for INTEGER→PREFIXED/sqlite uses printf, not LPAD."""
        expr = build_transform_expression(
            "order_id",
            JoinKeyFormat.INTEGER,
            JoinKeyFormat.PREFIXED_STRING,
            "sqlite",
            prefix="ORD",
            width=5,
        )
        assert expr is not None
        validate_sql_expression(expr, "order_id", "sqlite")

    @given(n=integer_keys())
    @h_settings(INVARIANT_SETTINGS["PBT-U5-05"])
    def test_pbt_u5_05_expression_validity_int_to_prefixed_duckdb(self, n: int) -> None:
        """build_transform_expression for INTEGER→PREFIXED/duckdb uses LPAD, not printf."""
        expr = build_transform_expression(
            "item_id",
            JoinKeyFormat.INTEGER,
            JoinKeyFormat.PREFIXED_STRING,
            "duckdb",
            prefix="ITEM",
            width=5,
        )
        assert expr is not None
        validate_sql_expression(expr, "item_id", "duckdb")
