# AI-DLC Inception (Sprint Week 8-9)

## Governance Reference
Use `planning/ai_dlc_playbook.md` as the source of truth for lifecycle gates, responsibilities, and required evidence.

## Press Release (Draft)
We built Oracle Forge, a multi-database analytics agent that answers enterprise-style natural language questions across PostgreSQL, MongoDB, SQLite, and DuckDB with verifiable trace output and benchmarked improvements on DataAgentBench.

## Honest FAQ (User)
1. What can this agent do now?
- It can accept DAB-style inputs, generate route plans, produce answers, and emit query traces.

2. What does it not do yet?
- It does not yet execute live cross-database queries end-to-end with full correctness guarantees.

3. How do we trust the output?
- Every answer includes a step trace and confidence, and harness logs are used for regression checks.

## Honest FAQ (Technical)
1. Biggest risk?
- Weak routing/query execution quality against real schemas.

2. Main dependency?
- Reliable database connectivity via MCP tools.

3. Hardest requirement?
- Cross-database joins with ill-formatted entity keys.

## Key Decisions
1. Use DAB-compatible function signature first to unblock benchmark integration.
2. Keep offline mode default for reproducible local tests.
3. Maintain corrections log as mandatory context input.

## Definition of Done (Baseline)
1. `agent/data_agent/dab_interface.py` exposes `run_agent(question, available_databases, schema_info)` and returns a dict with `answer`, `query_trace`, and `confidence`.
2. `python3 eval/run_trials.py --trials 5 --output results/smoke.json` runs without undocumented steps and writes structured per-query records.
3. `python3 eval/score_results.py --results results/smoke.json` writes `results/dab_detailed.json` and `results/dab_submission.json` with pass@1.
4. `kb/` contains `architecture/`, `domain/`, `evaluation/`, and `corrections/`, each with `CHANGELOG.md`.
5. `probes/probes.md` contains at least 15 probes spanning at least 3 failure categories.
6. Root `README.md` includes team roster, architecture diagram, clean-machine setup steps, and shared-server live-agent access info.

## Inception Gate Status
- Status: Approved for baseline.
- Approval evidence: `planning/mob_session_log.md` entry dated 2026-04-08.
- Next phase: Construction under playbook gate process.
