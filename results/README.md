# Results Directory Guide

This directory stores evaluation outputs, debug trial artifacts, and submission files.

## DAB Submission Status
- Submission file: `results/dab_submission.json` (and `team-cohere_gemini-2.0-flash-001_n5.json`)
- Coverage: 54 queries x 5 runs = 270 entries
- Structure: matches DAB reference format (`dataset`, `query`, `run`, `answer` as strings)
- Backbone LLM: `google/gemini-2.0-flash-001` (via OpenRouter)
- Dataset hints: used (`db_description_withhint.txt` injected per dataset)
- PR URL: https://github.com/ucbepic/DataAgentBench/pull/38
- PR title: `[Team Cohere] - TRP1 FDE Programme, April 2026`
- PR body draft: `results/dab_pr_draft.md`

### Score progression
| Iteration | Pass@1 | Trials passed | Notes |
|---|---:|---:|---|
| Initial submission | 14.07% | 38/270 | No schema-aliasing fix; many datasets at 0% |
| + view fix (partial rerun) | **15.19%** | **41/270** | Views expose DAB names over prefixed tables; bookreview 0→5, crmarenapro 0→2 |

The rerun was capped at 136/205 intended trials by OpenRouter weekly-credit
exhaustion across the two configured keys. Further improvements tracked as a
follow-up: (1) load `support.sql` / `books_info` / MongoDB tables that the
current load scripts skipped; (2) improve answer extraction so tool-call
results map cleanly to the ground truth format.

## Key Files
- `dab_benchmark_5trials.json`: Full 5-trial benchmark output.
- `dab_submission.json`: Submission-format file for DataAgentBench.
- `dab_pr_draft.md`: Ready-to-paste PR title/body for the benchmark submission.
- `smoke_check.json`: Smoke/baseline trial output.
- `score_progression.jsonl`: Auto-appended dated scoring entries.
- `score_progression.md`: Human-readable score progression with reproducibility notes.
- `debug_*.json`: Focused debugging trial runs for specific datasets/questions.

## Usage
- Treat these files as generated artifacts.
- Re-run `eval/run_trials.py` and `eval/score_results.py` to refresh benchmark outputs.
