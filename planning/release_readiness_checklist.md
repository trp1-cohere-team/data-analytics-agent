# Release Readiness Checklist

## Scope Control
- [ ] Release scope frozen
- [ ] No unreviewed high-impact changes pending
- [ ] Known limitations documented

## Reliability and Safety
- [ ] Unit tests pass: `python3 -m unittest discover -s tests -v`
- [ ] Tool policy still blocks mutating SQL
- [ ] Output contract (`answer`, `query_trace`, `confidence`) validated

## Evaluation Evidence
- [ ] Quick eval run complete (`run_trials.py --trials 5`)
- [ ] Stability eval run complete (`run_trials.py --trials 50`)
- [ ] Score summaries captured
- [ ] Regressions understood and accepted

## Artifacts
- [ ] Detailed results JSON saved under `results/`
- [ ] Submission JSON prepared when needed
- [ ] Score log updated
- [ ] Relevant docs updated in `planning/` and `kb/`

## Decision
- [ ] Release approved by primary owner
- [ ] Release approved by peer reviewer
- [ ] Rollback procedure confirmed

## Final Notes
- Release identifier:
- Date/time:
- Approvers:
- Post-release monitoring window:
