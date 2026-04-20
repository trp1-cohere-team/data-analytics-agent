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
import re
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


def _load_available_databases(dataset: str) -> list[dict]:
    """Return list of {name, type} descriptors from db_config.yaml.

    Preserves the per-database naming (e.g. ``business_database`` /
    ``review_database``) so the agent can cite the right source when
    constructing multi-DB workflows.
    """
    config_path = DAB_ROOT / f"query_{dataset}" / "db_config.yaml"
    if not config_path.exists():
        return []
    try:
        import yaml  # type: ignore
        with open(config_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except Exception as exc:
        logger.warning("Could not parse db_config.yaml for %s: %s", dataset, exc)
        return []

    clients = cfg.get("db_clients", {}) or {}
    items: list[dict] = []
    for name, spec in clients.items():
        if not isinstance(spec, dict):
            continue
        items.append({
            "name": str(name),
            "type": str(spec.get("db_type", "")),
        })
    return items


# Table names whose natural DAB names case-insensitively collide with other
# loaded base tables (e.g. a ``Lead`` table clashes with the ``LEAD`` stock
# ticker in DuckDB). For those we cannot create a view, so we tell the agent
# to use the prefixed name directly.
_COLLIDING_TABLE_OVERRIDES: dict[str, dict[str, str]] = {
    "crmarenapro": {"Lead": "crm_Lead"},
    "yelp": {"tip": "yelp_tip"},
}


def _load_dataset_description(dataset: str) -> tuple[str, str]:
    """Return (db_description, hints) for the dataset, or ("", "") on miss."""
    base = DAB_ROOT / f"query_{dataset}"
    description = ""
    hints = ""
    desc_path = base / "db_description.txt"
    hint_path = base / "db_description_withhint.txt"
    try:
        if desc_path.exists():
            description = desc_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("Could not read %s: %s", desc_path, exc)
    try:
        if hint_path.exists():
            raw = hint_path.read_text(encoding="utf-8").strip()
            # ``db_description_withhint.txt`` files start with ``HINTS:`` and
            # contain only the hint lines. Strip the header for cleaner prompts.
            hints = re.sub(r"^\s*HINTS\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
    except OSError as exc:
        logger.warning("Could not read %s: %s", hint_path, exc)

    overrides = _COLLIDING_TABLE_OVERRIDES.get(dataset)
    if overrides and description:
        lines = [
            f"- `{orig}` (as named in the description above) is stored as `{prefixed}`; "
            f"query `{prefixed}` directly."
            for orig, prefixed in overrides.items()
        ]
        description += (
            "\n\nLOCAL ENVIRONMENT NOTES (read carefully):\n" + "\n".join(lines)
        )
    return description, hints


def _answer_passes(answer: str, ground_truth: str) -> bool:
    """Heuristic pass check: ground truth substring in answer, or numeric match."""
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


def _write_results(path: str, results: list[dict]) -> None:
    """Atomic checkpoint write: write to ``<path>.tmp`` then rename.

    Prevents a partial file if the process is killed mid-write, so a
    resumed run can always read the last successful snapshot.
    """
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, default=str)
        os.replace(tmp, path)
    except OSError as exc:
        logger.error("Failed to write results to %s: %s", path, exc)


def _load_previous_results(path: str) -> list[dict]:
    """Load prior results (for resume). Returns empty list on any issue."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read prior results at %s: %s — starting fresh", path, exc)
    return []


def run_trials(
    datasets: list[str],
    trials: int,
    output_path: str,
    resume: bool = True,
) -> list[dict]:
    """Run agent trials across datasets and return results list.

    Resume: if ``resume=True`` (default) and ``output_path`` already
    contains a JSON array, previously completed (dataset, query_id, trial)
    triples are skipped. The file is checkpointed after every trial so
    partial progress survives SIGINT / kill.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    results: list[dict] = _load_previous_results(output_path) if resume else []
    done_keys: set[tuple] = {
        (r.get("dataset"), r.get("query_id"), r.get("trial"))
        for r in results
        if r.get("dataset") and r.get("query_id") and r.get("trial")
    }
    if done_keys:
        logger.info(
            "Resuming from %s — %d existing entries; will skip those",
            output_path, len(done_keys),
        )

    for dataset in datasets:
        dataset_dir = DAB_ROOT / f"query_{dataset}"
        if not dataset_dir.exists():
            logger.warning("Dataset dir not found: %s — skipping", dataset_dir)
            continue

        db_hints = _load_db_hints(dataset)
        available_dbs = _load_available_databases(dataset)
        description, hints_text = _load_dataset_description(dataset)
        dataset_context = {
            "dataset": dataset,
            "available_databases": available_dbs,
            "db_description": description,
            "hints": hints_text,
        }
        logger.info(
            "Dataset: %s | db_hints: %s | dbs: %s | schema_chars=%d hints_chars=%d",
            dataset, db_hints,
            [f"{d.get('name')}({d.get('type')})" for d in available_dbs],
            len(description), len(hints_text),
        )

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
                if (dataset, query_id, trial_num) in done_keys:
                    logger.info(
                        "Skip %s/%s trial %d/%d — already in results",
                        dataset, query_id, trial_num, trials,
                    )
                    continue
                logger.info(
                    "Running %s/%s trial %d/%d",
                    dataset, query_id, trial_num, trials,
                )
                t0 = time.monotonic()
                try:
                    result = run_agent(question, db_hints, dataset_context)
                    answer = result.answer
                    confidence = result.confidence
                    trace_id = result.trace_id
                    tool_call_trace = result.tool_calls
                    passed = _answer_passes(answer, ground_truth)
                except Exception as exc:
                    logger.error("Agent raised exception: %s", exc, exc_info=True)
                    answer = "Agent error"
                    confidence = 0.0
                    trace_id = ""
                    tool_call_trace = []
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
                    "tool_call_trace": tool_call_trace,
                    "pass": passed,
                    "ground_truth": ground_truth[:200],
                    "duration_s": round(duration_s, 3),
                })
                # Checkpoint after every trial so SIGINT / kill leaves a
                # consistent, resumable snapshot on disk.
                _write_results(output_path, results)

    # Final write (idempotent — ensures the file ends in a good state
    # even if no new trials ran, e.g. a fully-resumed no-op run).
    _write_results(output_path, results)
    logger.info("Results written to %s (%d entries)", output_path, len(results))

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
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Ignore any existing output file and start fresh.",
    )
    args = parser.parse_args()

    logger.info(
        "Starting trials: datasets=%s trials=%d output=%s resume=%s",
        args.datasets, args.trials, args.output, not args.no_resume,
    )
    run_trials(args.datasets, args.trials, args.output, resume=not args.no_resume)


if __name__ == "__main__":
    main()
