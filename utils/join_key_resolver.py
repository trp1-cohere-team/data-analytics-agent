from __future__ import annotations

import re


def normalize_identifier(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()
    if not text:
        return None

    digits = re.findall(r"\d+", text)
    if digits:
        return str(int(digits[0]))

    cleaned = re.sub(r"[^A-Z0-9]", "", text)
    return cleaned or None


def candidate_keys(value: object) -> set[str]:
    base = normalize_identifier(value)
    if base is None:
        return set()

    variants = {
        base,
        f"CUST-{base.zfill(5)}",
        f"CUST_{base.zfill(5)}",
        base.zfill(5),
    }
    return variants


def likely_match(left: object, right: object) -> bool:
    left_keys = candidate_keys(left)
    right_keys = candidate_keys(right)
    if not left_keys or not right_keys:
        return False
    return len(left_keys.intersection(right_keys)) > 0
