"""Local trial runner for the OracleForge Data Agent.

FR-07: Runs agent on local DAB query dirs with configurable trial count.
Acceptance criteria:
  python3 eval/run_trials.py --trials 2 --output results/smoke.json
  → completes without error, writes valid JSON to results/smoke.json

SEC-03: Structured logging.
SEC-15: Exception handling for all file I/O and agent calls.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure workspace root is importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent.data_agent.oracle_forge_agent import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Datasets available for local trial runs
DEFAULT_DATASETS = ["bookreview", "stockmarket"]

DAB_ROOT = _ROOT / "external" / "DataAgentBench"


def _load_question(query_dir: Path) -> str:
    """Load question text from query.json."""
    qfile = query_dir / "query.json"
    if not qfile.exists():
        return ""
    try:
        raw = qfile.read_text(encoding="utf-8").strip()
        # File may be raw string or JSON array/object
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                return parsed
            if isinstance(parsed, list) and parsed:
                return str(parsed[0])
            if isinstance(parsed, dict):
                return str(parsed.get("question", raw))
            return raw
        except json.JSONDecodeError:
            return raw
    except OSError as exc:
        logger.warning("Could not read question from %s: %s", qfile, exc)
        return ""


def _load_ground_truth(query_dir: Path) -> str:
    """Load ground truth from ground_truth.csv (first data row)."""
    gtfile = query_dir / "ground_truth.csv"
    if not gtfile.exists():
        return ""
    try:
        lines = [l for l in gtfile.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
        # DAB ground_truth.csv has no header — first line IS the data
        return lines[0] if lines else ""
    except OSError as exc:
        logger.warning("Could not read ground truth from %s: %s", gtfile, exc)
        return ""


def _load_db_hints(dataset: str) -> list[str]:
    """Extract db_type values from db_config.yaml as db hints."""
    config_path = DAB_ROOT / f"query_{dataset}" / "db_config.yaml"
    if not config_path.exists():
        return ["postgres", "sqlite"]
    try:
        import yaml  # type: ignore
        with open(config_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        clients = cfg.get("db_clients", {})
        return list({v.get("db_type", "") for v in clients.values() if v.get("db_type")})
    except Exception as exc:
        logger.warning("Could not parse db_config.yaml for %s: %s", dataset, exc)
        return ["postgres", "sqlite"]


def _answer_passes(answer: str, ground_truth: str) -> bool:
    """Heuristic pass check: ground truth substring in answer, or numeric match."""
    import re
    if not ground_truth:
        return False
    a = answer.strip().lower()
    g = ground_truth.strip().lower().strip('"').strip("'")

    # Basic substring check
    if g in a or a in g:
        return True

    # Multi-value ground truth (CSV row): check each field individually
    parts = [p.strip().strip('"').strip("'") for p in g.split(",")]
    matched = sum(1 for p in parts if p and p in a)
    if matched >= max(1, len(parts) // 2):
        return True

    # Numeric tolerance: compare floats with 1% relative tolerance
    try:
        g_float = float(g.replace(",", ""))
        for tok in re.findall(r"\d+\.?\d*", a):
            try:
                if abs(float(tok) - g_float) <= max(abs(g_float) * 0.01, 0.01):
                    return True
            except ValueError:
                pass
    except ValueError:
        pass

    return False


def run_trials(
    datasets: list[str],
    trials: int,
    output_path: str,
) -> list[dict]:
    """Run agent trials across datasets and return results list."""
    results: list[dict] = []
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    for dataset in datasets:
        dataset_dir = DAB_ROOT / f"query_{dataset}"
        if not dataset_dir.exists():
            logger.warning("Dataset dir not found: %s — skipping", dataset_dir)
            continue

        db_hints = _load_db_hints(dataset)
        logger.info("Dataset: %s | db_hints: %s", dataset, db_hints)

        # Find query subdirs
        query_dirs = sorted(
            [d for d in dataset_dir.iterdir() if d.is_dir() and d.name.startswith("query")],
            key=lambda d: d.name,
        )

        if not query_dirs:
            logger.warning("No query dirs found in %s", dataset_dir)
            continue

        for query_dir in query_dirs:
            question = _load_question(query_dir)
            if not question:
                logger.warning("No question in %s — skipping", query_dir)
                continue

            ground_truth = _load_ground_truth(query_dir)
            query_id = query_dir.name

            for trial_num in range(1, trials + 1):
                logger.info(
                    "Running %s/%s trial %d/%d",
                    dataset, query_id, trial_num, trials,
                )
                t0 = time.monotonic()
                try:
                    result = run_agent(question, db_hints)
                    answer = result.answer
                    confidence = result.confidence
                    trace_id = result.trace_id
                    passed = _answer_passes(answer, ground_truth)
                except Exception as exc:
                    logger.error("Agent raised exception: %s", exc, exc_info=True)
                    answer = "Agent error"
                    confidence = 0.0
                    trace_id = ""
                    passed = False

                duration_s = time.monotonic() - t0

                results.append({
                    "dataset": dataset,
                    "query_id": query_id,
                    "trial": trial_num,
                    "question": question[:200],
                    "answer": answer[:500],
                    "confidence": confidence,
                    "trace_id": trace_id,
                    "pass": passed,
                    "ground_truth": ground_truth[:200],
                    "duration_s": round(duration_s, 3),
                })

    # Write results
    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, default=str)
        logger.info("Results written to %s (%d entries)", output_path, len(results))
    except OSError as exc:
        logger.error("Failed to write results to %s: %s", output_path, exc)

    # Summary
    if results:
        total = len(results)
        passed = sum(1 for r in results if r["pass"])
        logger.info("Summary: %d/%d passed (pass rate=%.2f)", passed, total, passed / total)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="OracleForge local trial runner")
    parser.add_argument(
        "--trials", type=int, default=2,
        help="Number of trials per query (default: 2)",
    )
    parser.add_argument(
        "--output", type=str, default="results/smoke.json",
        help="Output JSON path (default: results/smoke.json)",
    )
    parser.add_argument(
        "--datasets", type=str, nargs="+", default=DEFAULT_DATASETS,
        help=f"Datasets to run (default: {DEFAULT_DATASETS})",
    )
    args = parser.parse_args()

    logger.info(
        "Starting trials: datasets=%s trials=%d output=%s",
        args.datasets, args.trials, args.output,
    )
    run_trials(args.datasets, args.trials, args.output)


if __name__ == "__main__":
    main()
