"""CLI entry point for the Evaluation Harness.

Usage:
    python -m eval.run_benchmark --agent-url http://localhost:8000
    python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 5
    python -m eval.run_benchmark --agent-url http://localhost:8000 --category NUMERIC
    python -m eval.run_benchmark --agent-url http://localhost:8000 --queries-path signal/

Exit codes:
    0 — benchmark complete, no regression detected
    1 — regression detected (pass@1 dropped vs previous run) — BR-U4-16
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from eval.harness import EvaluationHarness
from utils.benchmark_wrapper import load_dab_queries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.run_benchmark",
        description="Run DataAgentBench evaluation against the Oracle Forge agent.",
    )
    parser.add_argument(
        "--agent-url",
        required=True,
        help="Base URL of the agent under test (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Number of trials per query (default: 1)",
    )
    parser.add_argument(
        "--queries-path",
        default="signal/",
        help="Path to DAB queries JSON file or directory (default: signal/)",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Filter queries by category (e.g. NUMERIC, STRING, COMPLEX)",
    )
    return parser


def _print_result_summary(result, regression) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Benchmark Run: {result.run_id[:8]}...")
    print(f"  Agent URL    : {result.agent_url}")
    print(f"  Trials/query : {result.n_trials}")
    print(f"  Total queries: {result.total_queries}")
    print(f"  pass@1       : {result.pass_at_1:.4f}  ({result.pass_at_1 * 100:.1f}%)")
    print(f"{'=' * 60}")
    print(f"\n  Regression check:")
    print(f"    Previous score : {regression.previous_score:.4f}")
    print(f"    Current score  : {regression.current_score:.4f}")
    print(f"    Delta          : {regression.delta:+.4f}")
    status = "PASS" if regression.passed else "FAIL (REGRESSION DETECTED)"
    print(f"    Status         : {status}")
    if regression.failed_queries:
        print(f"    Regressed IDs  : {', '.join(regression.failed_queries)}")
    print()


async def _main(args: argparse.Namespace) -> int:
    category_filter = args.category
    queries = load_dab_queries(
        path=args.queries_path,
        filter=(lambda q: q.category == category_filter) if category_filter else None,
    )

    if not queries:
        print(f"No queries found at '{args.queries_path}'" +
              (f" with category='{category_filter}'" if category_filter else ""), file=sys.stderr)
        return 1

    harness = EvaluationHarness()
    result, regression = await harness.run(
        queries=queries,
        agent_url=args.agent_url,
        n_trials=args.trials,
    )

    _print_result_summary(result, regression)

    return 0 if regression.passed else 1  # BR-U4-16: non-zero exit on regression


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
