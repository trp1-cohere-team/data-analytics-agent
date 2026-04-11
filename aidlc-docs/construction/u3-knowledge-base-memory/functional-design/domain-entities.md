# Domain Entities
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11  
**Source**: `agent/models.py` (shared) + U3-specific additions

---

## Entity: KBDocument *(existing in models.py)*

**Purpose**: One markdown document loaded from the KB file system.

| Field | Type | Notes |
|---|---|---|
| `path` | `str` | Absolute or relative path to the `.md` file |
| `content` | `str` | Full UTF-8 text content of the document |
| `subdirectory` | `str` | Which KB subdir: `"architecture"` \| `"domain"` \| `"evaluation"` \| `"corrections"` |

**Derived**:
- `token_estimate: int = len(content) // 4` — injection test gate value

---

## Entity: CorrectionEntry *(existing in models.py)*

**Purpose**: One stored correction record appended to `kb/corrections/corrections.json`.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | UUID — unique across all sessions |
| `timestamp` | `float` | Unix epoch of the correction |
| `session_id` | `str` | Which agent session produced this correction |
| `failure_type` | `str` | `SYNTAX_ERROR` \| `JOIN_KEY_MISMATCH` \| `WRONG_DB_TYPE` \| `DATA_QUALITY` \| `UNKNOWN` |
| `original_query` | `str` | The query that failed |
| `corrected_query` | `str \| None` | The fixed query; `None` if no fix was found |
| `error_message` | `str` | Raw error from the execution engine |
| `fix_strategy` | `str` | Which strategy produced the fix |
| `attempt_number` | `int` | Which retry attempt (1–3) |
| `success` | `bool` | Whether the correction produced a passing result |

**On-Disk**: Stored as a JSON array in `kb/corrections/corrections.json`. Appended via atomic `.tmp` → rename (Q3=C). Never truncated.

---

## Entity: SessionTranscript *(new — U3 owned)*

**Purpose**: Persisted record of one agent query session including full trace and summary.

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | Matches the session_id used in `ReactState` |
| `timestamp` | `float` | Unix epoch when the session was saved |
| `history` | `list[TraceStep]` | Full list of ReAct iterations for this query (Q6=C) |
| `summary` | `str` | Brief text summary of the session outcome (Q6=C) |

**On-Disk**: `agent/memory/sessions/{session_id}.json` — write-once, never overwritten (KB-03).

---

## Entity: SessionMemory *(existing in models.py)*

**Purpose**: Consolidated in-memory view of the topic store — the "working memory" loaded per session.

| Field | Type | Notes |
|---|---|---|
| `successful_patterns` | `list[dict[str, Any]]` | Patterns from sessions that produced correct answers |
| `user_preferences` | `dict[str, Any]` | Accumulated preferences inferred from sessions |
| `query_corrections` | `list[dict[str, Any]]` | Recent correction summaries for context injection |

**On-Disk**: Sourced from three separate JSON files in `agent/memory/topics/`:
- `successful_patterns.json` → `SessionMemory.successful_patterns`
- `user_preferences.json` → `SessionMemory.user_preferences`
- `query_corrections.json` → `SessionMemory.query_corrections`

---

## Entity: TopicStore *(logical — no separate model class)*

**Purpose**: The three topic JSON files in `agent/memory/topics/` collectively form the consolidated long-term memory.

| File | Content | Consolidation Logic |
|---|---|---|
| `successful_patterns.json` | `list[dict]` — each entry is a successful query pattern with its plan | Merge: append patterns from sessions not already present |
| `user_preferences.json` | `dict` — key/value preferences | Merge: `dict.update()` (newer sessions overwrite older on conflict) |
| `query_corrections.json` | `list[dict]` — condensed correction entries | Merge: append entries from sessions, dedup by session_id |

---

## Entity: KBSubdirectory *(conceptual)*

**Purpose**: The four subdirectory slots in the KB file system.

| Subdir | Path | Purpose |
|---|---|---|
| `architecture` | `kb/architecture/` | Agent architecture and design reference docs |
| `domain` | `kb/domain/` | Domain knowledge (e.g. Yelp data schema docs) |
| `evaluation` | `kb/evaluation/` | Evaluation results and benchmark notes |
| `corrections` | `kb/corrections/` | Corrections log (corrections.json + CHANGELOG.md) |

Each subdir contains:
- One or more `.md` files (loaded by `KnowledgeBase.load_documents`)
- `CHANGELOG.md` — append-only log of injections (seeded with placeholder header at init, Q9=D)

---

## Entity Relationships

```
KnowledgeBase
  ├── _cache: dict[str, tuple[list[KBDocument], float]]   (subdir → (docs, loaded_at))
  ├── _corrections: list[CorrectionEntry]                 (in-memory mirror)
  └── kb_dir: Path                                        (points to kb/)

MemoryManager
  ├── _memory_dir: Path                                   (points to agent/memory/)
  ├── _sessions_dir: Path                                 (agent/memory/sessions/)
  ├── _topics_dir: Path                                   (agent/memory/topics/)
  └── _memory_index: Path                                 (agent/memory/MEMORY.md)

TopicStore (on disk, loaded as SessionMemory)
  ├── successful_patterns.json
  ├── user_preferences.json
  └── query_corrections.json

Sessions (on disk)
  └── sessions/{session_id}.json  → SessionTranscript
```
