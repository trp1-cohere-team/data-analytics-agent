# AI-DLC Operations Log

Reference playbook: `planning/ai_dlc_playbook.md`
Team operating roadmap: `planning/team_operating_system_roadmap.md`

## Active Team Roles
- Drivers: Nurye, Kemerya (Kemeriya)
- Intelligence Officers: Amare, Ephrata
- Signal Corps: Yohanis (Yohannes), Addisu

## Current state
- Baseline scaffolding completed.
- Local harness and tests available.
- Conductor + worker runtime split is implemented for planning vs execution responsibilities.
- Local sandbox server implemented at `sandbox/sandbox_server.py` with `/execute` contract.

## What changed from initial plan
- Added offline mode to avoid local network-related blocking.
- Added explicit routing-aware selection before execution planning.
- Added worker execution path and tests for routing/worker behavior.
- Added optional sandbox routing (`AGENT_USE_SANDBOX=1`) for isolated local SQL execution.

## Next sprint priorities
1. Integrate real DAB dataset loaders and schemas.
2. Implement live tool-calling execution over MCP toolbox.
3. Add regression suite against held-out real queries.

## Gate Decisions
### 2026-04-09
- Phase: Construction process hardening
- Decision: Adopt full AI-DLC playbook and templates for all future phase transitions.
- Alternatives considered:
  - Continue with ad-hoc planning notes only.
  - Use a minimal checklist without phase gates.
- Why this choice now:
  - The codebase now has enough runtime/eval complexity that informal process risks avoidable regressions.
- Risk created:
  - Higher process overhead for small changes.
- Monitoring:
  - Track cycle time and waiver count in future operations entries.

## Artifact Links
- Playbook: `planning/ai_dlc_playbook.md`
- Phase gate template: `planning/phase_gate_review_template.md`
- Release checklist: `planning/release_readiness_checklist.md`
- Postmortem template: `planning/postmortem_template.md`
