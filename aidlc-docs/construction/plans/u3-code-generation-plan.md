# U3 Code Generation Plan
# Unit 3 — Knowledge Base & Memory System

**Status**: In Progress  
**Date**: 2026-04-11

---

## Unit Context

**Requirements**: FR-03 (layer 2+3 context), FR-08 (KB structure + CHANGELOG + injection tests), NFR-03 (MEMORY.md pattern)  
**Dependencies**: `agent/models.py`, `agent/config.py` (shared), file system only — no network  
**Files Produced**:
- `agent/models.py` — add `SessionTranscript` model
- `agent/config.py` — add `memory_delete_after_consolidation`
- `agent/kb/__init__.py` — package marker
- `agent/kb/knowledge_base.py` — KnowledgeBase + all internal components
- `agent/memory/__init__.py` — package marker
- `agent/memory/manager.py` — MemoryManager + all internal components
- `tests/unit/strategies.py` — add `session_transcripts()` and `session_memory_objects()` strategies
- `tests/unit/test_knowledge_base.py` — unit tests + PBT-U3-01/02/03
- `tests/unit/test_memory_manager.py` — unit tests + PBT-U3-04/05/06
- `aidlc-docs/construction/u3-knowledge-base-memory/code/code-summary.md`

**Design Sources**:
- `aidlc-docs/construction/u3-knowledge-base-memory/functional-design/`
- `aidlc-docs/construction/u3-knowledge-base-memory/nfr-requirements/`
- `aidlc-docs/construction/u3-knowledge-base-memory/nfr-design/`

---

## Extension Compliance

| Extension | Status | Notes |
|---|---|---|
| Security Baseline | Enforced | FilenameGuard (SEC-U3-02), no content in logs (SEC-U3-01) |
| Property-Based Testing | Enforced | 6 blocking PBT properties (PBT-U3-01 through PBT-U3-06) |

---

## Code Generation Steps

- [x] **Step 1** — Update `agent/models.py`  
  Add `SessionTranscript(BaseModel)` to the `# Memory` section:  
  fields: `session_id: str`, `timestamp: float`, `history: list[TraceStep]`, `summary: str`

- [x] **Step 2** — Update `agent/config.py`  
  Add `memory_delete_after_consolidation: bool = Field(default=True, alias="MEMORY_DELETE_AFTER_CONSOLIDATION")`

- [x] **Step 3** — Create `agent/kb/__init__.py`  
  Package marker; exports `KnowledgeBase` at package level.

- [x] **Step 4** — Create `agent/kb/knowledge_base.py`  
  Implements:
  - `_read_text`, `_write_text`, `_replace_file`, `_mkdir`, `_glob` — AsyncFileIOWrapper helpers (Q1=A)
  - `_validate_filename` — FilenameGuard (SEC-U3-02, regex `^[\w\-. ]+\.md$`)
  - `_log_*` helpers — StructuredMemoryLogger for `agent.kb`
  - `KnowledgeBase.__init__` — sets up SubdirCache + CorrectionsStore + instance lock; calls `_ensure_kb_structure`
  - `_ensure_kb_structure` — creates 4 subdirs + seeds CHANGELOG.md (Q9=D)
  - `load_documents(subdir)` — hybrid cache with TTL invalidation (Q1=D); skips CHANGELOG.md
  - `inject_document(subdir, filename, content)` — FilenameGuard → 4k token gate → write → CHANGELOG append → cache invalidate
  - `append_correction(entry)` — acquires `self._corrections_lock` → atomic JSON array swap → update in-memory mirror (Q3=C, Q4=A, Q3=B lock)
  - `get_corrections()` — defensive copy of `self._corrections`
  - `_load_corrections_from_disk()` — reads corrections.json; tolerates corrupt entries (DC-01)

- [x] **Step 5** — Create `agent/memory/__init__.py`  
  Package marker; exports `MemoryManager` at package level.

- [x] **Step 6** — Create `agent/memory/manager.py`  
  Implements:
  - `_read_text`, `_write_text`, `_replace_file`, `_mkdir` — AsyncFileIOWrapper helpers (Q1=A, same pattern)
  - `_log_*` helpers — StructuredMemoryLogger for `agent.memory`
  - `MemoryManager.__init__` — creates dirs; bootstraps MEMORY.md; schedules `_run_autoDream` background task (Q7=B)
  - `save_session(session_id, history, summary)` — per-session-id lock (Q2=B) → existence check → write-once SessionTranscript JSON (Q5=A, Q6=C)
  - `load_session(session_id)` — reads `sessions/{id}.json`; returns `SessionTranscript | None`
  - `get_topics()` — loads 3 JSON topic files into `SessionMemory`; missing files return empty
  - `_run_autoDream()` — background task: find stale sessions → merge → `_write_topics_atomic` → MEMORY.md append → optional delete (Q7=B, Q8=C, Q4=D)
  - `_merge_session_into_topics(transcript, topics)` — additive merge by session_id dedup (MM-03)
  - `_write_topics_atomic(topics)` — StagingTransactionWriter: wipe `.staging/` → write 3 → rename all → cleanup (Q3=B, Q2=A staging)

- [x] **Step 7** — Update `tests/unit/strategies.py`  
  Add two new Hypothesis composite strategies:
  - `session_transcripts()` — generates `SessionTranscript` with valid `session_id` (UUID), `timestamp` (float), `history` (list[TraceStep] via existing strategy), `summary` (text)
  - `session_memory_objects()` — generates `SessionMemory` with lists of dicts and dict of strings

- [x] **Step 8** — Create `tests/unit/test_knowledge_base.py`  
  Unit tests + 3 PBT invariants:
  - `_ensure_kb_structure` creates all 4 subdirs + CHANGELOG.md files
  - `load_documents` returns empty on empty subdir; skips CHANGELOG; cache hit after first load; cache miss after TTL; cache invalidated after inject
  - `inject_document` writes file; appends CHANGELOG; raises on bad filename; raises on >4k tokens
  - `append_correction` increments count; dual write; locked concurrent safety
  - `get_corrections` returns defensive copy
  - Corrupt entry tolerance in `_load_corrections_from_disk`
  - **PBT-U3-01**: CorrectionEntry round-trip (200 examples)
  - **PBT-U3-02**: Append-only count invariant — N appends → len == N (100 examples, tmp dir)
  - **PBT-U3-03**: Injection token gate — >4k always raises; ≤4k always succeeds (150 examples)

- [x] **Step 9** — Create `tests/unit/test_memory_manager.py`  
  Unit tests + 3 PBT invariants:
  - `save_session` writes file; write-once (second call no-ops); per-session-id lock prevents race
  - `load_session` returns None for missing; returns SessionTranscript for saved
  - `get_topics` returns empty SessionMemory on fresh dir; returns merged data after consolidation
  - `_merge_session_into_topics` is additive (no removals); deduplicates by session_id
  - `_write_topics_atomic` writes all 3 files; wipes stale staging first; cleans up on success
  - autoDream skips sessions younger than threshold; processes stale ones; respects delete setting
  - **PBT-U3-04**: Write-once session count (100 examples)
  - **PBT-U3-05**: Topic merge idempotency (150 examples)
  - **PBT-U3-06**: SessionMemory round-trip (200 examples)

- [x] **Step 10** — Create `aidlc-docs/construction/u3-knowledge-base-memory/code/code-summary.md`  
  Summary table of all generated files, key design decisions, PBT properties.

---

## Completion Criteria

- All 10 steps marked [x]
- Application code in `agent/kb/` and `agent/memory/` (never in aidlc-docs/)
- Security rules: FilenameGuard on all inject calls, no content in logs
- 6 PBT properties present across both test files
- All design decisions implemented (Q1=D, Q2=B, Q3=C, Q4=A, Q5=A, Q6=C, Q7=B, Q8=C, Q9=D, NFR Q1=A, Q2=A, Q3=B)
