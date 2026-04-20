"""Merge worker outputs and build the DAB submission JSON.

Produces two files:
  - results/dab_benchmark_5trials.json: full merged results (all worker fields)
  - results/dab_submission.json:        rubric-shaped (dataset, query_id, trial, answer)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER_FILES = [
    ROOT / "results" / "dab_gemini_w1.json",
    ROOT / "results" / "dab_gemini_w2.json",
    ROOT / "results" / "dab_gemini_w3.json",
    ROOT / "results" / "dab_gemini_w4.json",
]
MERGED = ROOT / "results" / "dab_benchmark_5trials.json"
SUBMISSION = ROOT / "results" / "dab_submission.json"

EXPECTED_TOTAL = 270

def main() -> int:
    merged: list[dict] = []
    seen: set[tuple] = set()
    for f in WORKER_FILES:
        if not f.exists():
            print(f"[warn] missing {f.name}", file=sys.stderr)
            continue
        entries = json.loads(f.read_text())
        for r in entries:
            key = (r["dataset"], r["query_id"], r["trial"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
        print(f"[info] {f.name}: {len(entries)} entries")

    merged.sort(key=lambda r: (r["dataset"], r["query_id"], r["trial"]))
    MERGED.write_text(json.dumps(merged, indent=2, default=str))
    print(f"[ok] wrote {MERGED.name} ({len(merged)} entries)")

    submission = []
    for r in merged:
        qid = r["query_id"]
        query_num = qid[len("query"):] if qid.startswith("query") else qid
        submission.append({
            "dataset": r["dataset"],
            "query": query_num,
            "run": str(int(r["trial"]) - 1),
            "answer": r["answer"],
        })
    SUBMISSION.write_text(json.dumps(submission, indent=2, default=str))
    print(f"[ok] wrote {SUBMISSION.name} ({len(submission)} entries)")

    if len(merged) != EXPECTED_TOTAL:
        print(f"[warn] expected {EXPECTED_TOTAL} entries, got {len(merged)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
