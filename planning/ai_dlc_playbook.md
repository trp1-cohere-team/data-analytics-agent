# AI-DLC Full Lifecycle Playbook

## Purpose
This playbook defines how Oracle Forge is built, validated, released, and improved using an end-to-end AI Development Lifecycle (AI-DLC).

Goals:
- Keep development fast without losing quality control.
- Tie each phase to objective evidence in this repository.
- Make go/no-go decisions explicit and auditable.

Scope:
- Applies to all changes that can impact answer quality, query routing, DB tool execution, and benchmark outcomes.
- Applies to local development, benchmark runs, and submission preparation.

## Lifecycle Map
1. Inception: define target behavior, risks, and measurable success.
2. Construction: implement features safely with tests and traces.
3. Evaluation: measure correctness and stability against harnesses.
4. Release: freeze, verify, and publish reproducible artifacts.
5. Learning: capture failures and feed corrections into next cycle.

## Repository Anchors
- Inception notes: `planning/inception.md`
- Operations log: `planning/operations.md`
- Team operating roadmap: `planning/team_operating_system_roadmap.md`
- Mob approval log: `planning/mob_session_log.md`
- Agent mission/contract: `agent/AGENT.md`
- Runtime orchestration: `agent/runtime/conductor.py`
- Step execution worker: `agent/runtime/worker.py`
- Routing logic: `agent/data_agent/router.py`, `agent/runtime/routing.py`
- Evaluation harness: `eval/README.md`, `eval/run_trials.py`, `eval/run_dab_benchmark.py`, `eval/score_results.py`
- Output artifacts: `results/README.md`
- Corrections memory: `kb/corrections/corrections_log.md`

## Roles and Ownership (RACI-lite)
- Product/Challenge Owner
  - Owns problem framing, success metrics, and release decision.
- Runtime Owner
  - Owns conductor/worker/tooling behavior and safety policy.
- Evaluation Owner
  - Owns benchmark runs, scoring, and regression evidence.
- Knowledge Base Owner
  - Owns corrections, domain layer updates, and memory hygiene.
- Reviewer (Peer)
  - Owns gate review independence and sign-off integrity.

Minimum sign-off rule:
- Every phase gate needs two reviewers:
  - One primary owner for the phase.
  - One peer from a different ownership area.

## Phase 1: Inception
### Entry Criteria
- New feature, bug class, or benchmark regression is identified.
- Problem statement and impact are understandable in one paragraph.

### Required Activities
- Document what users need and current limitations.
- List top risks with expected failure modes.
- Define quantitative success criteria.
- Decide constraints (offline mode, tool availability, deadlines).

### Required Artifacts
- `planning/inception.md` updated with:
  - User FAQ
  - Technical FAQ
  - Key decisions
  - Definition of Done
- `planning/mob_session_log.md` entry for approval of Inception gate.

### Exit Gate (Go/No-Go)
Go only if all are true:
- Problem and non-goals are explicit.
- Success metric is measurable using existing repo tools.
- Top 3 risks have mitigation strategy.
- Owners are named for Construction and Evaluation.

## Phase 2: Construction
### Entry Criteria
- Inception gate approved.
- Work scope is small enough to complete with tests and traceability.

### Required Activities
- Implement minimal change set first.
- Keep orchestration boundaries explicit:
  - Conductor decides route and planning scope.
  - Worker executes query steps.
- Add or update tests near changed behavior.
- Preserve non-mutating query policy.

### Required Artifacts
- Code changes in `agent/`, `utils/`, `kb/` as needed.
- Tests in `tests/` for new/changed behavior.
- Trace stages that make failures diagnosable.

### Mandatory Local Checks
Run all checks before phase gate request:
```bash
python3 -m unittest discover -s tests -v
```

Optional focused run for rapid loop:
```bash
python3 -m unittest tests/test_runtime_tooling.py -v
python3 -m unittest tests/test_worker.py -v
```

### Exit Gate (Go/No-Go)
Go only if all are true:
- New behavior is covered by tests.
- All tests pass locally.
- No unresolved critical safety regressions (policy bypass, mutating SQL execution).
- Trace output still explains route, plan, and execution outcomes.

## Phase 3: Evaluation
### Entry Criteria
- Construction gate approved.
- Build is stable enough for repeated trial runs.

### Required Activities
- Run smoke evaluation on held-out sample.
- Run multi-trial local benchmark for stability.
- If available, run DAB smoke on real query folders.
- Compare metrics to previous baseline.

### Mandatory Commands
Quick local evaluation:
```bash
python3 eval/run_trials.py --trials 5 --output results/local_results_5.json
python3 eval/score_results.py --results results/local_results_5.json
```

Stability evaluation:
```bash
python3 eval/run_trials.py --trials 50 --output results/local_results_50.json
python3 eval/score_results.py --results results/local_results_50.json
```

DAB smoke evaluation (if dataset is available):
```bash
python3 eval/run_dab_benchmark.py \
  --dab-root external/DataAgentBench \
  --query-limit 1 \
  --trials 2 \
  --output-detailed results/dab_smoke_detailed.json \
  --output-submission results/dab_smoke_submission.json
```

### Required Artifacts
- Results JSON outputs in `results/`.
- Score summary update in `eval/score_log.md` or `results/score_log.md`.
- Short evaluation note in `planning/operations.md`.

### Exit Gate (Go/No-Go)
Go only if all are true:
- Evaluation commands complete without runtime exceptions.
- Metrics are stable or intentionally regressed with documented rationale.
- Top new failure patterns are cataloged for Learning phase.

## Phase 4: Release
### Entry Criteria
- Evaluation gate approved.
- Team agrees that quality is sufficient for challenge submission or milestone tag.

### Required Activities
- Freeze planned scope (no opportunistic feature additions).
- Verify reproducibility commands from clean environment assumptions.
- Ensure submission artifacts are consistent and complete.

### Release Checklist
- Runtime tests pass.
- Evaluation outputs exist and are timestamped/traceable.
- Submission file generated (if release is for DAB submission).
- `results/README.md` suggested artifacts are present where applicable.
- Known limitations are documented.

### Exit Gate (Go/No-Go)
Go only if all are true:
- Artifact completeness is verified.
- Gate approvers sign release decision in operations log.
- Rollback plan is prepared.

## Phase 5: Learning
### Entry Criteria
- Release completed or Evaluation exposed meaningful failures.

### Required Activities
- Diagnose root causes from trace and validation logs.
- Append corrections to corrections log.
- Update KB layer documents and changelogs when needed.
- Translate top failure classes into tests.

### Required Artifacts
- `kb/corrections/corrections_log.md` updated.
- KB changelogs under `kb/**/CHANGELOG.md` updated when semantics changed.
- New regression tests added for repeated failures.

### Exit Gate (Go/No-Go)
Go only if all are true:
- Top 3 failure categories have concrete follow-up actions.
- At least one prevention action is added (test, policy, or planner improvement).
- Next Inception scope is informed by evidence, not intuition.

## Quality Gates Matrix
- Severity S0 (Blocker)
  - Examples: crashing runs, invalid output contract, mutating SQL allowed.
  - Action: stop release, patch before continuing.
- Severity S1 (High)
  - Examples: wrong DB routing causing systematic wrong answers.
  - Action: require fix or formal waiver with owner sign-off.
- Severity S2 (Medium)
  - Examples: occasional self-correction miss, sparse trace detail.
  - Action: can release with documented mitigation and follow-up issue.
- Severity S3 (Low)
  - Examples: non-critical wording, minor docs drift.
  - Action: backlog unless bundling into current cycle is low risk.

## Operational Cadence
- Daily:
  - construction updates in `planning/operations.md`
  - quick tests on changed components
- Per merge candidate:
  - full unit test run
  - quick eval (`--trials 5`)
- Per milestone/release:
  - stability eval (`--trials 50`)
  - release checklist completion
  - learning capture

## Decision Records
When making high-impact changes (routing policy, tool policy, planner strategy), add a short record in `planning/operations.md` with:
- Date
- Decision
- Alternatives considered
- Why this choice now
- Risk created
- How risk is monitored

## Rollback and Recovery
If post-release regression is detected:
1. Halt new release candidate changes.
2. Re-run last known-good evaluation command set.
3. Compare traces for route, plan, execution divergence.
4. Revert or patch minimal failing component.
5. Log incident and corrective action in operations + corrections log.

## Metrics to Track Every Cycle
- pass@1 (from score script)
- any-run success rate (for multi-trial runs)
- run-level accuracy
- tool invocation success rate
- self-correction recovery rate
- percentage of answers with complete trace stages

## PR and Review Minimums
Before requesting review:
- Include what changed and why.
- Include exact commands run and summary of outcomes.
- Include risk notes for routing, tool policy, and result synthesis.
- Include follow-up tasks if any gate waiver is requested.

Reviewer checklist:
- Verify changed behavior has tests.
- Verify no policy boundary was weakened unintentionally.
- Verify evaluation evidence exists for behavior-impacting changes.
- Verify documentation updates for lifecycle phase artifacts.

## Templates
Use these companion files:
- `planning/phase_gate_review_template.md`
- `planning/release_readiness_checklist.md`
- `planning/postmortem_template.md`
- `planning/team_operating_system_roadmap.md`

## Adoption Steps (Recommended)
1. Use this playbook for the next active change immediately.
2. Fill one gate review template per phase transition.
3. Enforce release checklist for every benchmark submission attempt.
4. Run learning template after every failed smoke or failed milestone run.
