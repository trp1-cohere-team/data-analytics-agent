"""Text processing utilities for KB retrieval.

FR-09: Keyword extraction, document overlap scoring, filename matching, freshness bonus.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words (common English — minimal set)
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
        "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such", "no",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "because", "if", "while", "about", "up", "its", "it", "this", "that",
        "these", "those", "i", "me", "my", "we", "our", "you", "your", "he",
        "him", "his", "she", "her", "they", "them", "their", "what", "which",
        "who", "whom",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def extract_keywords(text: str) -> list[str]:
    """Extract deduplicated keywords from *text*, filtering stop words.

    Returns an empty list for empty input.
    All returned keywords are lowercase.
    """
    if not text:
        return []

    tokens = _TOKEN_RE.findall(text.lower())
    seen: set[str] = set()
    result: list[str] = []
    for tok in tokens:
        if len(tok) < 2:
            continue
        if tok in _STOP_WORDS:
            continue
        if tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


def score_overlap(keywords: list[str], document: str) -> float:
    """Score how many *keywords* appear in *document*.

    Returns a float in [0.0, 1.0].  Returns 0.0 when *keywords* is empty.
    """
    if not keywords:
        return 0.0

    doc_lower = document.lower()
    matched = sum(1 for kw in keywords if kw in doc_lower)
    return matched / len(keywords)


def filename_stem_overlap(keywords: list[str], filename: str) -> float:
    """Score keyword overlap against the filename stem.

    The stem is split on ``_`` and ``-`` after stripping the extension.
    Returns a float in [0.0, 1.0].  Returns 0.0 when *keywords* is empty.
    """
    if not keywords:
        return 0.0

    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem_tokens = set(re.split(r"[_\-]", stem))
    matched = sum(1 for kw in keywords if kw in stem_tokens)
    return matched / len(keywords)


def freshness_bonus(file_path: str) -> float:
    """Return a freshness bonus in [0.0, 0.3] based on file modification time.

    Returns 0.0 if the file does not exist (SEC-15 safe fallback).
    """
    try:
        mtime = os.path.getmtime(file_path)
    except (OSError, FileNotFoundError):
        return 0.0

    age_days = (time.time() - mtime) / 86400.0
    if age_days <= 1:
        return 0.3
    if age_days <= 7:
        return 0.2
    if age_days <= 30:
        return 0.1
    return 0.0
