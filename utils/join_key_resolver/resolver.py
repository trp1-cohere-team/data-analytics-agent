from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationResult:
    original: str | int
    normalized: str
    strategy: str


class JoinKeyResolver:
    """
    Normalize entity identifiers across heterogeneous systems.

    Supported examples:
    - 123 -> "123"
    - "CUST-00123" -> "123"
    - "000123" -> "123"
    - "prd_a12" -> "PRD_A12"
    """

    CUSTOMER_PREFIX_PATTERN = re.compile(r"^CUST-0*(\d+)$", re.IGNORECASE)
    NUMERIC_PADDING_PATTERN = re.compile(r"^0+(\d+)$")

    def normalize_customer_id(self, value: str | int) -> NormalizationResult:
        if isinstance(value, int):
            return NormalizationResult(
                original=value,
                normalized=str(value),
                strategy="int_to_string",
            )

        text = value.strip()

        match = self.CUSTOMER_PREFIX_PATTERN.match(text)
        if match:
            return NormalizationResult(
                original=value,
                normalized=str(int(match.group(1))),
                strategy="strip_customer_prefix_and_padding",
            )

        if text.isdigit():
            return NormalizationResult(
                original=value,
                normalized=str(int(text)),
                strategy="strip_numeric_padding",
            )

        raise ValueError(f"Unsupported customer ID format: {value!r}")

    def normalize_product_code(self, value: str) -> NormalizationResult:
        normalized = value.strip().upper()
        return NormalizationResult(
            original=value,
            normalized=normalized,
            strategy="uppercase_normalization",
        )

    def normalize_order_id(self, value: str | int) -> NormalizationResult:
        if isinstance(value, int):
            return NormalizationResult(
                original=value,
                normalized=str(value),
                strategy="int_to_string",
            )

        text = value.strip()
        if text.isdigit():
            return NormalizationResult(
                original=value,
                normalized=str(int(text)),
                strategy="strip_numeric_padding",
            )

        raise ValueError(f"Unsupported order ID format: {value!r}")

    def keys_match(
        self,
        left: str | int,
        right: str | int,
        entity_type: str,
    ) -> bool:
        if entity_type == "customer":
            return (
                self.normalize_customer_id(left).normalized
                == self.normalize_customer_id(right).normalized
            )

        if entity_type == "product":
            if not isinstance(left, str) or not isinstance(right, str):
                return False
            return (
                self.normalize_product_code(left).normalized
                == self.normalize_product_code(right).normalized
            )

        if entity_type == "order":
            return (
                self.normalize_order_id(left).normalized
                == self.normalize_order_id(right).normalized
            )

        raise ValueError(f"Unsupported entity_type: {entity_type!r}")
