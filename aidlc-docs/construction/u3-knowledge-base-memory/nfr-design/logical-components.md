# Logical Components
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11

---

## Component Map

```
agent/kb/
  knowledge_base.py
    KnowledgeBase              ← top-level; owns cache + corrections + lock
      SubdirCache              ← dict[str, (list[KBDocument], float)] — hybrid cache
      CorrectionsStore         ← list[CorrectionEntry] + asyncio.Lock (instance-level)
      FilenameGuard            ← regex validation for inject_document
      AsyncFileIO helpers      ← _read_text, _write_text, _replace_file, _mkdir, _glob

agent/memory/
  manager.py
    MemoryManager              ← top-level; owns sessions + topics + autoDream task
      SessionRegistry          ← dict[str, asyncio.Lock] + sessions dir path
      TopicStoreReader         ← get_topics() — loads 3 JSON files into SessionMemory
      StagingTransactionWriter ← _write_topics_atomic — staging dir + atomic rename
      autoDreamTask            ← asyncio background task scheduled at __init__
      MemoryLogger             ← structured log helpers (_log_* functions)
```

---

## KnowledgeBase Component Interfaces

### KnowledgeBase (top-level)

```python
class KnowledgeBase:
    def __init__(self, kb_dir: str | Path, refresh_interval_s: int = 60) -> None: ...

    async def load_documents(self, subdir: str) -> list[KBDocument]: ...
    # Hybrid cache (Q1=D): returns cached list if age < refresh_interval_s;
    # reloads from disk (via asyncio.to_thread) otherwise.
    # Skips CHANGELOG.md. Empty subdir returns [].

    async def inject_document(self, subdir: str, filename: str, content: str) -> None: ...
    # FilenameGuard check → token budget check (4k limit) → write file →
    # append CHANGELOG.md → invalidate cache for subdir.

    async def append_correction(self, entry: CorrectionEntry) -> None: ...
    # Acquires self._corrections_lock → read-modify → atomic write → update mirror.

    def get_corrections(self) -> list[CorrectionEntry]: ...
    # Returns defensive copy of self._corrections (synchronous — reads in-memory only).

    async def load_corrections_from_disk(self) -> list[CorrectionEntry]: ...
    # Forces a fresh read from corrections.json (bypasses in-memory mirror).
    # Used internally at __init__ only.
```

**Invariants**:
- `get_corrections()` always reflects the in-memory mirror — never stale vs last `append_correction` call.
- `load_documents` never returns CHANGELOG.md as a KBDocument.
- `inject_document` always invalidates the subdir cache after a successful write.

---

### SubdirCache (internal)

```python
# State: self._cache: dict[str, tuple[list[KBDocument], float]]
# Key: subdir name ("architecture" | "domain" | "evaluation" | "corrections")
# Value: (documents, loaded_at_monotonic)

# Cache is invalidated (key deleted) when:
#   - inject_document succeeds for that subdir
#   - Explicit clear (testing only)
```

---

### CorrectionsStore (internal)

```python
# State:
self._corrections: list[CorrectionEntry]         # in-memory mirror
self._corrections_lock: asyncio.Lock             # instance-level (Q3=B)
self._corrections_path: Path                     # kb/corrections/corrections.json
```

---

### FilenameGuard (internal)

```python
_SAFE_FILENAME_RE = re.compile(r'^[\w\-. ]+\.md$')

def _validate_filename(filename: str) -> None:
    """Raises ValueError on unsafe filenames (path traversal, non-MD, etc.)."""
    if not _SAFE_FILENAME_RE.match(filename):
        raise ValueError(f"Unsafe filename: {filename!r}")
    if ".." in filename:
        raise ValueError(f"Path traversal in filename: {filename!r}")
```

---

## MemoryManager Component Interfaces

### MemoryManager (top-level)

```python
class MemoryManager:
    def __init__(self, memory_dir: str | Path, max_age_days: int = 7,
                 delete_after_consolidation: bool = True) -> None: ...
    # Creates dirs, bootstraps MEMORY.md, schedules _run_autoDream() background task.

    async def save_session(
        self,
        session_id: str,
        history: list[TraceStep],
        summary: str,
    ) -> None: ...
    # Write-once: acquires per-session lock → existence check → write SessionTranscript JSON.

    async def load_session(self, session_id: str) -> SessionTranscript | None: ...
    # Returns None if not found.

    async def get_topics(self) -> SessionMemory: ...
    # Loads successful_patterns.json, user_preferences.json, query_corrections.json.
    # Returns empty SessionMemory if files don't exist.

    async def _run_autoDream(self) -> None: ...
    # Background task: find stale sessions → merge → StagingTransactionWriter → cleanup.

    async def _write_topics_atomic(self, topics: SessionMemory) -> None: ...
    # StagingTransactionWriter pattern: wipe .staging/ → write 3 files → rename all → cleanup.
```

---

### SessionRegistry (internal)

```python
# State:
self._sessions_dir: Path                         # agent/memory/sessions/
self._session_locks: dict[str, asyncio.Lock]     # per-session-id locks (Q2=B)
```

---

### StagingTransactionWriter (internal)

```python
# Used by: _write_topics_atomic
# Staging directory: self._topics_dir / ".staging"
#
# Protocol:
#   1. shutil.rmtree(.staging, ignore_errors=True)  — wipe stale (Q2=A)
#   2. .staging.mkdir()
#   3. write_text(.staging/successful_patterns.json, ...)
#   4. write_text(.staging/user_preferences.json, ...)
#   5. write_text(.staging/query_corrections.json, ...)
#   6. replace(.staging/X → topics/X) for all three
#   7. shutil.rmtree(.staging)  — always, in finally block
```

---

### autoDreamTask (internal)

```python
# Scheduled in MemoryManager.__init__ as:
#   asyncio.ensure_future(self._run_autoDream())
#
# Algorithm:
#   1. Scan sessions_dir/*.json for files with timestamp < now - (max_age_days * 86400)
#   2. For each stale session: load → _merge_session_into_topics
#   3. _write_topics_atomic(merged_topics)
#   4. Append consolidation summary block to MEMORY.md (append mode)
#   5. If delete_after_consolidation: delete session files (in to_thread)
#   6. Log autodream_complete
#
# Error handling: wrapped in try/except; errors logged at ERROR, task never crashes agent.
```

---

## models.py Addition Required

One new model added to `agent/models.py` during U3 code generation:

```python
class SessionTranscript(BaseModel):
    """Persisted record of one agent query session. Write-once."""
    session_id: str
    timestamp: float                  # Unix epoch when saved
    history: list[TraceStep]          # Full ReAct trace (Q6=C)
    summary: str                      # Caller-provided text summary (Q6=C)
```

Added to the `# Memory` section of models.py, after `SessionMemory`.

---

## Dependency Graph

```
KnowledgeBase
  ├── SubdirCache              (in-process dict)
  ├── CorrectionsStore
  │     └── asyncio.Lock      (instance-level, Q3=B)
  ├── FilenameGuard            (regex, pure function)
  └── AsyncFileIO helpers ──────→ asyncio.to_thread → pathlib.Path (Q1=A)

MemoryManager
  ├── SessionRegistry
  │     └── dict[str, asyncio.Lock]  (per-session-id, Q2=B)
  ├── TopicStoreReader ────────────→ AsyncFileIO → json.loads → SessionMemory
  ├── StagingTransactionWriter
  │     ├── AsyncFileIO (write/replace)
  │     └── shutil.rmtree (via to_thread) — stale staging wipe (Q2=A)
  ├── autoDreamTask ───────────────→ TopicStoreReader + StagingTransactionWriter
  │                                   + MEMORY.md append + session file delete
  └── MemoryLogger ────────────────→ logging.getLogger("agent.memory")

agent/models.py
  └── SessionTranscript (new) ─────→ consumed by MemoryManager.save_session / load_session
```

---

## Security Implementation

### FilenameGuard (SEC-U3-02)
- Regex `^[\w\-. ]+\.md$` — blocks any filename containing `/`, `\`, `..`, or non-markdown extension.
- Double-check for `".."` substring as belt-and-suspenders against exotic regex edge cases.
- Applied before any disk I/O in `inject_document`.

### No Content in Logs (SEC-U3-01, OBS-U3-04)
- All `_log_*` helper functions in StructuredMemoryLogger only accept typed scalar parameters (counts, IDs, elapsed_ms).
- No `str` parameters that could accidentally carry content — content fields are never passed to log helpers.
