"""Simple CLI for OracleForge agent."""

from __future__ import annotations

import argparse
import json

from agent.data_agent.oracle_forge_agent import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OracleForge against a single question")
    parser.add_argument("question", type=str, help="Natural language question")
    parser.add_argument(
        "--db-hints",
        type=str,
        default='["postgres"]',
        help="JSON array of DB hints, e.g. '[\"postgres\", \"duckdb\"]'",
    )
    args = parser.parse_args()

    try:
        db_hints = json.loads(args.db_hints)
        if not isinstance(db_hints, list):
            raise ValueError("db-hints must decode to a list")
    except Exception:
        db_hints = ["postgres"]

    result = run_agent(args.question, [str(x) for x in db_hints])
    print(json.dumps({
        "answer": result.answer,
        "confidence": result.confidence,
        "trace_id": result.trace_id,
        "tool_calls": result.tool_calls,
        "failure_count": result.failure_count,
    }, indent=2))


if __name__ == "__main__":
    main()
