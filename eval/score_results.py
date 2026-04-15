"""pass@1 scorer for OracleForge DAB results.

FR-07: Reads results JSON, computes per-query pass@1 and overall score.
Outputs dab_detailed.json and dab_submission.json.

Acceptance criteria:
  python3 eval/score_results.py --results results/smoke.json
  → prints valid pass@1 in [0.0, 1.0]

PBT-03 invariant: pass@1 is always in [0.0, 1.0].
SEC-03: Structured logging.
SEC-15: Exception handling for file I/O.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def compute_pass_at_1(results: list[dict]) -> tuple[float, dict]:
    """Compute pass@1 from a list of trial result dicts.

    pass@1 per query: True if any trial passed.
    Overall pass@1: fraction of queries where at least 1 trial passed.

    Parameters
    ----------
    results:
        List of trial result dicts with keys: dataset, query_id, trial, pass.

    Returns
    -------
    tuple[float, dict]
        ``(overall_pass_at_1, per_query_details)``
        overall_pass_at_1 is guaranteed to be in [0.0, 1.0].
    """
    if not results:
        return 0.0, {}

    # Group by (dataset, query_id)
    queries: dict[str, list[bool]] = {}
    for r in results:
        key = f"{r.get('dataset', 'unknown')}/{r.get('query_id', 'unknown')}"
        if key not in queries:
            queries[key] = []
        queries[key].append(bool(r.get("pass", False)))

    per_query: dict[str, dict] = {}
    passed_count = 0
    for key, trial_passes in queries.items():
        passed = any(trial_passes)
        per_query[key] = {
            "passed": passed,
            "trials": len(trial_passes),
            "pass_count": sum(trial_passes),
        }
        if passed:
            passed_count += 1

    total_queries = len(queries)
    overall = passed_count / total_queries if total_queries > 0 else 0.0

    # Invariant: clamp to [0.0, 1.0] (PBT-03)
    overall = max(0.0, min(1.0, overall))

    return overall, per_query


def score(results_path: str, output_dir: str | None = None) -> float:
    """Load results file, compute scores, write output files, return pass@1.

    SEC-15: All file I/O wrapped in try/except.
    """
    try:
        with open(results_path, "r", encoding="utf-8") as fh:
            results = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load results from %s: %s", results_path, exc)
        return 0.0

    if not isinstance(results, list):
        logger.error("Results file must contain a JSON array")
        return 0.0

    overall, per_query = compute_pass_at_1(results)

    # Per-dataset rollup
    dataset_scores: dict[str, dict] = {}
    for key, details in per_query.items():
        ds = key.split("/")[0]
        if ds not in dataset_scores:
            dataset_scores[ds] = {"total": 0, "passed": 0}
        dataset_scores[ds]["total"] += 1
        if details["passed"]:
            dataset_scores[ds]["passed"] += 1

    dataset_pass_at_1 = {
        ds: round(v["passed"] / v["total"], 4) if v["total"] > 0 else 0.0
        for ds, v in dataset_scores.items()
    }

    detailed = {
        "pass_at_1": round(overall, 4),
        "total_queries": len(per_query),
        "passed_queries": sum(1 for d in per_query.values() if d["passed"]),
        "dataset_scores": dataset_pass_at_1,
        "per_query": per_query,
    }
    submission = {
        "pass_at_1": round(overall, 4),
        "dataset_scores": dataset_pass_at_1,
    }

    # Determine output directory
    if output_dir is None:
        output_dir = str(Path(results_path).parent)

    try:
        os.makedirs(output_dir, exist_ok=True)
        detailed_path = os.path.join(output_dir, "dab_detailed.json")
        submission_path = os.path.join(output_dir, "dab_submission.json")
        with open(detailed_path, "w", encoding="utf-8") as fh:
            json.dump(detailed, fh, indent=2)
        with open(submission_path, "w", encoding="utf-8") as fh:
            json.dump(submission, fh, indent=2)
        logger.info("Wrote %s and %s", detailed_path, submission_path)
    except OSError as exc:
        logger.warning("Could not write output files: %s", exc)

    return overall


def main() -> None:
    parser = argparse.ArgumentParser(description="OracleForge pass@1 scorer")
    parser.add_argument(
        "--results", type=str, required=True,
        help="Path to results JSON file",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory for dab_detailed.json and dab_submission.json",
    )
    args = parser.parse_args()

    pass_at_1 = score(args.results, args.output_dir)
    print(f"pass@1 = {pass_at_1:.4f}")
    logger.info("Scoring complete: pass@1=%.4f", pass_at_1)


if __name__ == "__main__":
    main()
