"""MultiPassRetriever — 3-vocabulary-pass search over the corrections log.

Runs three keyword passes (failure vocab, correction vocab, domain vocab),
scores each entry using static tiers plus an IDF multiplier once the corpus
reaches 20+ entries, deduplicates, ranks, and returns the top 10.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from agent.models import CorrectionEntry, KeywordScore

# ---------------------------------------------------------------------------
# Fixed vocabulary sets
# ---------------------------------------------------------------------------

_PASS1_BASE: frozenset[str] = frozenset(
    {
        "syntax error", "join", "mismatch", "failed", "exception",
        "wrong", "incorrect", "empty result", "null", "type error",
        "postgres", "sqlite", "mongodb", "duckdb",
    }
)

_PASS2_BASE: frozenset[str] = frozenset(
    {
        "corrected", "fixed", "resolved", "rewritten", "rerouted",
        "reformatted", "coalesce", "ifnull", "fallback", "retry",
        "syntax", "join_key", "data_quality",
    }
)

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were",
        "for", "of", "in", "on", "at", "to", "from",
        "and", "or", "but", "not", "with", "by",
    }
)

_HIGH_VALUE_TERMS: frozenset[str] = frozenset(
    {
        "join", "mismatch", "pipeline", "aggregate", "foreign key",
        "cust-", "composite", "uuid", "prefixed", "cross-db",
        "syntax error", "dialect", "reroute", "coalesce",
    }
)

_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _keyword_tier_score(keyword: str) -> int:
    """Return 3 for high-value domain terms, 1 for common correction terms."""
    kw_lower = keyword.lower()
    if any(h in kw_lower for h in _HIGH_VALUE_TERMS):
        return 3
    return 1


def _compute_idf(corrections: list[CorrectionEntry]) -> dict[str, float]:
    """Compute IDF weights over the corrections corpus.

    Returns empty dict when corpus < 20 (static tiers only — MPR-03).
    Uses +1 smoothing to prevent division by zero.
    """
    if len(corrections) < 20:
        return {}

    n = len(corrections)
    doc_freq: dict[str, int] = defaultdict(int)
    for entry in corrections:
        text = entry.searchable_text()
        for term in set(text.split()):
            doc_freq[term] += 1

    return {term: math.log((n + 1) / (df + 1)) for term, df in doc_freq.items()}


def _build_pass_queries(query: str) -> list[list[str]]:
    """Generate 3 keyword lists from the input query.

    Pass 1: failure/error vocabulary + DB type names found in query.
    Pass 2: correction/fix vocabulary + failure type names if detected.
    Pass 3: domain-specific terms extracted from the query itself.
    """
    query_lower = query.lower()

    # Pass 1: base failure vocab + DB names mentioned in query
    db_names = [db for db in ("postgres", "sqlite", "mongodb", "duckdb") if db in query_lower]
    pass1 = list(_PASS1_BASE) + db_names

    # Pass 2: base correction vocab + failure types if mentioned
    failure_types = [
        ft for ft in ("syntax", "join_key", "data_quality", "routing") if ft in query_lower
    ]
    pass2 = list(_PASS2_BASE) + failure_types

    # Pass 3: domain terms extracted from query
    words = query.split()
    domain_terms = {
        w for w in words
        if len(w) > 4
        and w.lower() not in _STOP_WORDS
        and not w.isdigit()
        and w.isalnum()
    }
    snake_terms = set(_SNAKE_CASE_RE.findall(query))
    pass3 = list(domain_terms | snake_terms)

    return [pass1, pass2, pass3]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_corrections(
    query: str,
    corrections: list[CorrectionEntry],
    passes: int = 3,
) -> list[CorrectionEntry]:
    """Search corrections log using N vocabulary passes and return ranked results.

    Rules:
    - Always runs all passes (MPR-01)
    - Deduplicates before ranking (MPR-02)
    - IDF applied only when corpus >= 20 entries (MPR-03)
    - Returns at most 10 entries (MPR-04)
    - Zero-score entries excluded (MPR-05)
    - Tiebreaker: more recent timestamp ranks higher (MPR-06)
    - Keyword matching is case-insensitive (MPR-07)
    """
    if not corrections:
        return []

    pass_queries = _build_pass_queries(query)[:passes]
    idf_table = _compute_idf(corrections)

    # Accumulate scores per entry
    scores: dict[str, KeywordScore] = {}

    for keywords in pass_queries:
        for entry in corrections:
            entry_text = entry.searchable_text()
            for keyword in keywords:
                if keyword.lower() in entry_text:
                    tier = _keyword_tier_score(keyword)
                    idf_mult = idf_table.get(keyword.lower(), 1.0)
                    score_delta = tier * idf_mult
                    if entry.id not in scores:
                        scores[entry.id] = KeywordScore(
                            entry_id=entry.id,
                            raw_score=0.0,
                            timestamp=entry.timestamp,
                            entry=entry,
                        )
                    scores[entry.id].raw_score += score_delta

    # Filter zero-score, sort by score desc then timestamp desc (MPR-05, MPR-06)
    ranked = sorted(
        (ks for ks in scores.values() if ks.raw_score > 0),
        key=lambda ks: (-ks.raw_score, -ks.timestamp),
    )
    return [ks.entry for ks in ranked[:10]]  # MPR-04: cap at 10
