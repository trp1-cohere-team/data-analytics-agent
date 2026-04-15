"""Full DAB benchmark runner for the OracleForge Data Agent.

FR-07: Runs all 12 DAB datasets with configurable trials.
Wraps run_trials.py for full benchmark execution.

SEC-03: Structured logging.
SEC-15: Exception handling throughout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from eval.run_trials import run_trials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

ALL_DATASETS = [
    "bookreview",
    "crmarenapro",
    "DEPS_DEV_V1",
    "GITHUB_REPOS",
    "googlelocal",
    "PANCANCER_ATLAS",
    "PATENTS",
    "stockindex",
    "stockmarket",
    "yelp",
    "agnews",
    "music_brainz_20k",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="OracleForge full DAB benchmark runner")
    parser.add_argument(
        "--trials", type=int, default=5,
        help="Number of trials per query (default: 5)",
    )
    parser.add_argument(
        "--output", type=str, default="results/dab_benchmark.json",
        help="Output JSON path (default: results/dab_benchmark.json)",
    )
    parser.add_argument(
        "--datasets", type=str, nargs="+", default=ALL_DATASETS,
        help="Datasets to run (default: all 12)",
    )
    args = parser.parse_args()

    logger.info(
        "Starting full DAB benchmark: %d datasets, %d trials each",
        len(args.datasets), args.trials,
    )

    results = run_trials(args.datasets, args.trials, args.output)

    # Per-dataset summary
    dataset_scores: dict[str, dict] = {}
    for r in results:
        ds = r["dataset"]
        if ds not in dataset_scores:
            dataset_scores[ds] = {"total": 0, "passed": 0}
        dataset_scores[ds]["total"] += 1
        if r["pass"]:
            dataset_scores[ds]["passed"] += 1

    print("\n=== DAB Benchmark Results ===")
    total_all = 0
    passed_all = 0
    for ds, scores in sorted(dataset_scores.items()):
        t = scores["total"]
        p = scores["passed"]
        rate = p / t if t > 0 else 0.0
        total_all += t
        passed_all += p
        print(f"  {ds}: {p}/{t} pass@trial (rate={rate:.2f})")

    overall = passed_all / total_all if total_all > 0 else 0.0
    print(f"\nOverall: {passed_all}/{total_all} (pass@1={overall:.3f})")


if __name__ == "__main__":
    main()
