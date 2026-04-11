# Team Operating System Roadmap (Weeks 8-9 Challenge)

## Source of Truth
This roadmap is aligned to:
- `planning/ai_dlc_playbook.md`

Challenge window: **Weeks 8-9 (April 2026)**

Challenge deadlines (UTC):
1. **Interim submission:** Tuesday, April 14, 2026 - 21:00 UTC
2. **Final submission:** Saturday, April 18, 2026 - 21:00 UTC

## Team Role Assignments
- **Drivers:** Nurye, Kemeriya
- **Intelligence Officers:** Yohannes, Amare
- **Signal Corps:** Ephrata, Addisu

## Operating Principles (Non-Negotiable)
1. We run one daily mob session (minimum 1 hour, every working day).
2. AI-DLC gates are human-approved in mob sessions, not asynchronously.
3. No phase transition without explicit team approval.
4. Documentation is first-class: decisions and evidence must be written, not implied.
5. Every benchmark/evaluation claim must be backed by reproducible artifacts.

## AI-DLC Operating Cycle For This Challenge
The challenge uses three AI-DLC phases per sprint:
1. **Inception:** define what we build, risks, and done criteria.
2. **Construction:** build with mob discipline and shared ownership.
3. **Operations:** verify, evaluate, document outcomes and next sprint changes.

Gate policy:
- Gate A: Inception -> Construction requires full team approval.
- Gate B: Construction -> Operations requires full team approval.
- Gate evidence must be logged in `planning/mob_session_log.md` and `planning/operations.md`.

## Daily Mob Session Protocol (Required)
Duration: minimum 60 minutes per working day.

Structure:
1. **10 min (Intelligence Officers):** KB updates + ecosystem insights.
2. **10 min (Signal Corps):** what was posted, response, and external signal.
3. **40 min (Drivers with full-team co-pilot):** construction/operations execution.

## Weekly Rhythm (Weeks 8-9)
### Week 8 Focus
- Establish runnable agent baseline on shared server.
- Ship KB v1 (architecture) and KB v2 (domain).
- Ship initial evaluation harness and first baseline score.
- Produce Inception approval records and construction logs.
- Prepare interim submission package.

### Week 9 Focus
- Expand to adversarial probes and correction-loop hardening.
- Run DAB benchmark at required trial depth.
- Record measurable score improvement vs baseline.
- Publish complete Signal Corps portfolio.
- Prepare final submission package.

## Role Operating Charters (Challenge-Aligned)
### Drivers (Nurye, Kemeriya)
Primary accountability:
- Running codebase and deployment on shared server.
- AI-DLC Inception document per sprint.
- Evaluation harness with trace + score progression.
- Benchmark submission run and results packaging.

Mandatory outputs:
1. Running agent accessible on shared server.
2. AI-DLC Inception docs with approval records.
3. Evaluation harness outputs with regression evidence.
4. DAB results package for submission.

### Intelligence Officers (Yohannes, Amare)
Primary accountability:
- Knowledge Base quality and injection readiness.
- Shared utility library and adversarial probes.
- Failure taxonomy, corrections log maintenance, benchmark intelligence.

Mandatory outputs:
1. KB v1 architecture layer.
2. KB v2 domain layer.
3. KB v3 corrections log.
4. At least 3 reusable utilities (documented/tested).
5. At least 15 adversarial probes across at least 3 DAB failure categories.
6. Weekly ecosystem report for Monday mob session.

### Signal Corps (Ephrata, Addisu)
Primary accountability:
- Internal and external communication of technical progress.
- Daily visibility and engagement logs.
- End-of-week and final engagement summaries.

Mandatory outputs:
1. Internal Slack-style daily post (what shipped, stuck, next).
2. Minimum 2 technical X threads per week.
3. One substantive LinkedIn/Medium article per member across the two weeks (>=600 words).
4. Community participation log with substantive links.
5. External engagement summary at end of Week 9.

## Milestone Roadmap
## Milestone 1: Interim Package (Due Tuesday, April 14, 2026 - 21:00 UTC)
Required repo state includes:
1. `README.md` with members/roles, architecture diagram, setup, shared-server link.
2. `agent/` with working baseline agent and multi-db direction (minimum practical coverage progressing).
3. `kb/` with architecture/domain foundation and changelogs.
4. `eval/` with harness and first baseline score log.
5. `planning/` with AI-DLC Inception docs and approval records.
6. `utils/` with shared utilities (minimum 3 modules, documented).
7. `signal/` with Week 8 engagement artifacts.

Mob checkpoint before submission:
- All three roles confirm deliverables are present.
- Signal Corps confirms evidence links are complete.
- Team records final interim gate decision.

## Milestone 2: Final Package (Due Saturday, April 18, 2026 - 21:00 UTC)
Adds to interim:
1. `probes/` with 15+ adversarial probes and fix documentation.
2. `results/` with DAB run artifacts, score progression, PR link evidence.
3. `kb/` updated with corrections-log impact (KB v3).
4. `eval/` updated with progression and regression status.
5. `signal/` complete portfolio including long-form articles and benchmark communications.
6. Benchmark PR opened to DataAgentBench with required metadata.

Mob checkpoint before submission:
- Score progression is explicitly shown from baseline to final.
- Corrections log shows behavioral improvements.
- Signal Corps verifies all public links and accessibility.
- Team records final gate decision and retrospective note.

## Command Ownership by Role
### Drivers
```bash
python3 -m unittest discover -s tests -v
```

### Intelligence Officers
```bash
python3 eval/run_trials.py --trials 5 --output results/local_results_5.json
python3 eval/score_results.py --results results/local_results_5.json
python3 eval/run_trials.py --trials 50 --output results/local_results_50.json
python3 eval/score_results.py --results results/local_results_50.json
```

Benchmark run path (when dataset is available):
```bash
python3 eval/run_dab_benchmark.py \
  --dab-root external/DataAgentBench \
  --trials 50 \
  --output-detailed results/dab_full_50_detailed.json \
  --output-submission results/dab_full_50_submission.json
```

### Signal Corps
Daily verification targets:
- `planning/operations.md`
- `planning/mob_session_log.md`
- `signal/engagement_log.md`
- `signal/community_participation_log.md`
- `signal/resource_acquisition_report.md`

## Handoff Contracts
### Intelligence Officers -> Drivers
Must include:
1. Failing query and failure category.
2. Evidence trace/result.
3. Suggested correction and expected outcome.

### Drivers -> Signal Corps
Must include:
1. What shipped today.
2. Evidence command outputs (summary).
3. Risks/blockers and tomorrow plan.

### Signal Corps -> Team
Must include:
1. Daily status snapshot.
2. External signals worth acting on.
3. Missing evidence artifacts before next gate.

## Governance and Merge Rules
1. Every behavior-impacting change needs test evidence.
2. Every gate needs mob-session sign-off evidence.
3. Before merging to `main`, require:
- one Driver review,
- one Intelligence Officer review,
- Signal Corps evidence-completeness check.

## Scoreboard (Tracked Daily in Week 9)
1. pass@1
2. run-level accuracy
3. query trace completeness
4. tool execution success rate
5. self-correction recovery rate
6. open S1/S0 issues

## Immediate Action Checklist (Today)
1. Confirm this roadmap as team operating contract in mob session.
2. Create/update current sprint Inception document and get gate approval.
3. Assign interim milestone owners per directory (`agent`, `kb`, `eval`, `planning`, `utils`, `signal`).
4. Run one baseline evaluation cycle and log results.
5. Start daily operating cadence immediately.
