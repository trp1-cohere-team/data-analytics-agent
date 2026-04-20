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
| + view fix (partial rerun) | 15.19% | 41/270 | Views expose DAB names over prefixed tables; bookreview 0→5, crmarenapro 0→2 |
| + round-2 agent improvements (2026-04-20) | **28.15%** | **76/270** | 429/503/504 backoff in `_call_llm`; 4 KB cap on KB docs (corrections_log no longer inflates prompts ~70×); `_scrub_leaked_llm_output` strips code fences / plan comments / raw dict dumps; evidence-mode prompt requires in-SQL computation; added `kb/domain/{pancancer,patents,agnews}-patterns.md`. |

Per-dataset pass@1 at 28.15% snapshot:
stockmarket 25/25 · stockindex 10/15 · googlelocal 9/20 · music_brainz_20k 5/15 ·
bookreview 5/15 · GITHUB_REPOS 6/20 · DEPS_DEV_V1 2/10 · crmarenapro 9/65 ·
yelp 4/35 · PATENTS 1/15 · PANCANCER_ATLAS 0/15 · agnews 0/20.

Remaining failures on PANCANCER_ATLAS and agnews are analytical-reasoning limits
(in-SQL chi-square; text-based LLM classification) rather than schema gaps, so
KB docs alone did not move them — follow-up work is specialised solver pipelines
or a stronger reasoning model.

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
