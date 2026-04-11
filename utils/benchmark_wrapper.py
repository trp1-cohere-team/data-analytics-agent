"""BenchmarkWrapper — simplified Python API for running DAB query subsets.

Delegates all scoring and tracing to EvaluationHarness (U4).
Default trial counts are developer-friendly (5 or 3), not the production 50.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from agent.models import BenchmarkResult, DABQuery


def load_dab_queries(
    filter: Callable[[DABQuery], bool] | None = None,
    path: str | Path = "signal",
) -> list[DABQuery]:
    """Load DAB queries from the signal/ directory.

    Args:
        filter: Optional predicate to select a subset of queries.
        path: Directory containing DAB query JSON files.
    """
    queries: list[DABQuery] = []
    signal_dir = Path(path)
    if not signal_dir.exists():
        return queries

    for json_file in sorted(signal_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    queries.append(DABQuery(**item))
            elif isinstance(data, dict):
                queries.append(DABQuery(**data))
        except Exception:
            continue

    if filter is not None:
        queries = [q for q in queries if filter(q)]
    return queries


def run_subset(
    agent_url: str,
    query_ids: list[str],
    trials: int = 5,
) -> BenchmarkResult:
    """Run a named subset of DAB queries against the agent.

    BW-01: default trials=5 (developer default, not production 50).
    BW-02: delegates fully to EvaluationHarness.
    """
    from eval.harness import EvaluationHarness
    import asyncio

    queries = load_dab_queries(filter=lambda q: q.id in query_ids)
    harness = EvaluationHarness()
    return asyncio.run(harness.run_benchmark(agent_url, queries, n_trials=trials))


def run_single(
    agent_url: str,
    query_id: str,
    trials: int = 3,
) -> BenchmarkResult:
    """Run a single DAB query. BW-01: default trials=3."""
    return run_subset(agent_url, [query_id], trials=trials)


def run_category(
    agent_url: str,
    category: str,
    trials: int = 5,
) -> BenchmarkResult:
    """Run all queries of a given category."""
    from eval.harness import EvaluationHarness
    import asyncio

    queries = load_dab_queries(filter=lambda q: q.category == category)
    harness = EvaluationHarness()
    return asyncio.run(harness.run_benchmark(agent_url, queries, n_trials=trials))
