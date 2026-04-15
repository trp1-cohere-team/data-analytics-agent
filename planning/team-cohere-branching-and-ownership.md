# Team Cohere Branching and Ownership Plan

This file splits the OracleForge codebase by role and member so each person can commit and push from their own branch with clean merge boundaries.

## Team Roles
- Drivers: `nurye`, `kemeriya`
- Intelligence Officers: `ephrata`, `amare`
- Signal Corps: `addisu`, `yohannes`

## Branch Naming Convention
- `cohere/driver/nurye`
- `cohere/driver/kemeriya`
- `cohere/intelligence/ephrata`
- `cohere/intelligence/amare`
- `cohere/signal/addisu`
- `cohere/signal/yohannes`

## Merge Strategy
1. Everyone branches from `master` baseline.
2. Open PRs into `master` only.
3. Keep PR scope inside owned paths.
4. Rebase before merge to avoid cross-branch conflicts.
5. Use squash merge only for noisy fixup branches; normal merge for milestone branches.

## Ownership by Role

### Drivers
- Runtime and orchestration:
  - `agent/runtime/`
  - `agent/data_agent/oracle_forge_agent.py`
  - `agent/AGENT.md`
  - `sandbox/`
  - `tools.yaml`
  - `README.md`

Driver split:
- `nurye`: conductor/runtime core, live pipeline wiring, DB server integration
- `kemeriya`: sandbox path, agent facade polish, tool policy/runtime safeguards, README runbook

### Intelligence Officers
- Knowledge and evaluation science:
  - `kb/`
  - `probes/`
  - `tests/test_probes.py`
  - `tests/test_properties.py`
  - `docs/`
  - `aidlc-docs/`

Intelligence split:
- `ephrata`: domain KB + join-key glossary + adversarial probes + PBT updates
- `amare`: architecture/evaluation KB + aidlc narrative consistency + probe analysis docs

### Signal Corps
- Reporting and public-facing evidence:
  - `results/`
  - `eval/`
  - `aidlc-docs/construction/build-and-test/`
  - `planning/`

Signal split:
- `addisu`: evaluation runs, score snapshots, benchmark JSON packaging
- `yohannes`: writeups, build/test instructions, submission-ready reporting docs

## 10-Commit Milestone Ladder per Member

Each member should keep at least 10 meaningful commits in their branch, with one objective per commit.

### Driver: nurye
1. runtime baseline alignment
2. conductor loop reliability update
3. cross-db orchestration enhancement
4. event trace quality improvements
5. timeout/failure handling hardening
6. live stockmarket trial fix
7. regression test additions for runtime
8. runtime refactor cleanup
9. docs sync for runtime decisions
10. final integration + smoke verification

### Driver: kemeriya
1. sandbox/client baseline
2. sandbox health-path improvements
3. input validation hardening
4. tool policy guard refinements
5. AGENT.md behavior clarifications
6. oracle_forge_agent facade cleanup
7. README execution flow update
8. integration tests for sandbox behavior
9. error-path polish
10. final runtime integration checks

### Intelligence: ephrata
1. domain KB baseline pass
2. stockmarket schema clarification
3. join-key glossary enrichment
4. probes category 1 expansion
5. probes category 2 expansion
6. probes category 3 expansion
7. test_probes updates
8. property-based test additions
9. corrections log refinement
10. KB changelog + evidence update

### Intelligence: amare
1. architecture KB baseline pass
2. evaluation KB cleanup
3. aidlc requirement trace mapping
4. docs consistency pass across FR/NFR/SEC
5. probe-analysis writeups
6. test rationale docs update
7. u4/u5 code-summary alignment
8. aidlc-state progression update
9. final docs QA pass
10. release note for knowledge artifacts

### Signal: addisu
1. eval runner baseline audit
2. scoring script validation pass
3. result artifact naming standard
4. t1 smoke report artifact
5. t2 smoke report artifact
6. pass@1 trend table generation
7. benchmark submission pack prep
8. build-and-test report update
9. result directory cleanup/curation
10. final evidence snapshot

### Signal: yohannes
1. build instructions baseline
2. integration instructions update
3. performance test notes
4. demo checklist draft
5. submission checklist draft
6. final report skeleton
7. role deliverables mapping
8. communication-ready summary docs
9. final report polish
10. merge-ready documentation QA

## Member Setup Commands

Run this before each member starts work:

```bash
git checkout master
git pull origin master
git checkout -b cohere/<role>/<name>
git config user.name "<member name>"
git config user.email "<member email>"
```

## Push Commands

```bash
git push -u origin cohere/<role>/<name>
```

## PR Title Format
- `[Cohere][Driver][nurye] <short summary>`
- `[Cohere][Intelligence][ephrata] <short summary>`
- `[Cohere][Signal][addisu] <short summary>`

