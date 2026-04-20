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
# Original gemini-2.0-flash worker outputs (the 270 that were submitted first)
WORKER_FILES = [
    ROOT / "results" / "dab_gemini_w1.json",
    ROOT / "results" / "dab_gemini_w2.json",
    ROOT / "results" / "dab_gemini_w3.json",
    ROOT / "results" / "dab_gemini_w4.json",
]
# View-fix rerun outputs. Each entry wins over the original entry with the same
# (dataset, query_id, trial) key; where the rerun is missing a triple, we keep
# the original so the submission stays at 270 entries.
RERUN_FILES = [
    ROOT / "results" / "dab_viewfix_w1.json",
    ROOT / "results" / "dab_viewfix_w2.json",
    ROOT / "results" / "dab_viewfix_w3.json",
    ROOT / "results" / "dab_viewfix_w4.json",
]
MERGED = ROOT / "results" / "dab_benchmark_5trials.json"
SUBMISSION = ROOT / "results" / "dab_submission.json"
SUBMISSION_NAMED = ROOT / "results" / "team-cohere_gemini-2.0-flash-001_n5.json"

EXPECTED_TOTAL = 270

def main() -> int:
    base: dict[tuple, dict] = {}
    for f in WORKER_FILES:
        if not f.exists():
            print(f"[warn] missing base {f.name}", file=sys.stderr)
            continue
        entries = json.loads(f.read_text())
        for r in entries:
            key = (r["dataset"], r["query_id"], r["trial"])
            if key not in base:
                base[key] = r
        print(f"[info] base {f.name}: {len(entries)} entries")

    rerun_count = 0
    for f in RERUN_FILES:
        if not f.exists():
            continue
        entries = json.loads(f.read_text())
        for r in entries:
            key = (r["dataset"], r["query_id"], r["trial"])
            base[key] = r  # rerun overwrites
            rerun_count += 1
        print(f"[info] rerun {f.name}: {len(entries)} entries (overwriting base)")
    if rerun_count:
        print(f"[info] {rerun_count} rerun entries merged in")

    merged = list(base.values())

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
    SUBMISSION_NAMED.write_text(json.dumps(submission, indent=2, default=str))
    print(f"[ok] wrote {SUBMISSION_NAMED.name} ({len(submission)} entries)")

    passed = sum(1 for r in merged if r.get("pass"))
    print(f"[stats] pass@1 (trial-level) = {passed}/{len(merged)} = {100*passed/len(merged):.2f}%")

    if len(merged) != EXPECTED_TOTAL:
        print(f"[warn] expected {EXPECTED_TOTAL} entries, got {len(merged)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
