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
1. Agent callable matches DAB-style input/output contract.
2. Multi-trial runner works for 5 and 50 trial settings.
3. Score script outputs pass@1 summary.
4. KB structure has 4 required layers with changelogs.
5. Probe library has at least 15 probes across >=3 categories.

## Inception Gate Status
- Status: Approved for baseline.
- Approval evidence: `planning/mob_session_log.md` entry dated 2026-04-08.
- Next phase: Construction under playbook gate process.
