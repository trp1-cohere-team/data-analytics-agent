"""Knowledge base retrieval with weighted ranking.

FR-09: Load kb/ subdirectories, keyword-based retrieval, freshness-weighted ranking.
SEC-15: Safe file I/O with error handling.
"""

from __future__ import annotations

import logging
import os
from collections import namedtuple
from typing import Optional

from agent.data_agent.config import KB_ROOT
from utils.text_utils import (
    extract_keywords,
    filename_stem_overlap,
    freshness_bonus,
    score_overlap,
)

logger = logging.getLogger(__name__)

KBDocument = namedtuple("KBDocument", ["path", "content", "category"])

# Scoring weights (BR-U2-06)
_W_CONTENT = 0.6
_W_FILENAME = 0.25
_W_FRESHNESS = 0.15

_ALL_CATEGORIES = ("architecture", "domain", "evaluation", "corrections")


def _load_category_docs(category: str) -> list[KBDocument]:
    """Load all .md documents from a single KB category directory."""
    category_dir = os.path.join(KB_ROOT, category)
    docs: list[KBDocument] = []

    if not os.path.isdir(category_dir):
        logger.debug("KB category directory not found: %s", category_dir)
        return docs

    try:
        entries = os.listdir(category_dir)
    except OSError as exc:
        logger.warning("Failed to list KB directory %s: %s", category_dir, exc)
        return docs

    for entry in sorted(entries):
        if not entry.endswith(".md"):
            continue
        filepath = os.path.join(category_dir, entry)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
            docs.append(KBDocument(path=filepath, content=content, category=category))
        except OSError as exc:
            logger.warning("Failed to read KB file %s: %s", filepath, exc)

    return docs


def load_layered_kb_context(
    query: str,
    categories: Optional[list[str]] = None,
) -> list[tuple[str, float]]:
    """Retrieve KB documents ranked by relevance to *query*.

    Returns a list of ``(document_content, relevance_score)`` tuples
    sorted by descending score.  Only documents with score > 0.0 are
    included.

    Parameters
    ----------
    query : str
        The user query to match against.
    categories : list[str] | None
        KB categories to search.  Defaults to all four categories.
    """
    if not query:
        return []

    cats = categories or list(_ALL_CATEGORIES)
    keywords = extract_keywords(query)
    if not keywords:
        return []

    scored: list[tuple[str, float]] = []

    for category in cats:
        for doc in _load_category_docs(category):
            content_score = score_overlap(keywords, doc.content)
            fname_score = filename_stem_overlap(keywords, doc.path)
            fresh = freshness_bonus(doc.path)
            final = (
                _W_CONTENT * content_score
                + _W_FILENAME * fname_score
                + _W_FRESHNESS * fresh
            )
            if final > 0.0:
                scored.append((doc.content, final))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
