# Tech Stack Decisions
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11

---

## No New Package Dependencies

U3 uses Python stdlib only — no new packages added to `pyproject.toml`.

| Capability | Library | Already in Use? |
|---|---|---|
| File I/O | `pathlib.Path` | Yes (U5, U2) |
| JSON serialization | `json` (stdlib) | Yes |
| Async locking | `asyncio.Lock` (stdlib) | Yes (U2 pattern) |
| Logging | `logging` (stdlib) | Yes |
| Regex (filename guard) | `re` (stdlib) | Yes |
| Pydantic model serialization | `pydantic` | Yes |
| Type hints | `typing`, `__future__` annotations | Yes |

**Rationale**: U3 is file-system only — no network, no DB, no external services. All required capabilities are already available in the installed environment from U5/U2.

---

## Concurrency Implementation

### asyncio.Lock for corrections (Q1=D)

```python
# Module-level lock in knowledge_base.py
_CORRECTIONS_LOCK = asyncio.Lock()

async def append_correction(self, entry: CorrectionEntry) -> None:
    async with _CORRECTIONS_LOCK:
        # read-modify-write cycle
        ...
```

**Why not filelock**: filelock is a cross-process lock (useful for multi-process deployments). The agent is single-process (uvicorn in single-worker mode), so `asyncio.Lock` is sufficient and adds zero dependencies.

### defaultdict(asyncio.Lock) for sessions (Q2=B)

```python
# In MemoryManager.__init__
self._session_locks: dict[str, asyncio.Lock] = {}

async def save_session(self, session_id: str, ...) -> None:
    if session_id not in self._session_locks:
        self._session_locks[session_id] = asyncio.Lock()
    async with self._session_locks[session_id]:
        ...
```

**Lock cleanup**: Session locks are not cleaned up after use (they're lightweight). The dict is bounded by the number of unique session_ids processed in one process lifetime — acceptable for a single-query-server pattern.

---

## autoDream Staging Pattern (Q3=B)

```python
STAGING_DIR = self._topics_dir / ".staging"

# Write all three to staging first
STAGING_DIR.mkdir(exist_ok=True)
for filename, data in topic_files:
    (STAGING_DIR / filename).write_text(...)

# All staging writes succeeded — atomic rename to final locations
for filename in topic_filenames:
    (STAGING_DIR / filename).replace(self._topics_dir / filename)

# Clean up staging dir
shutil.rmtree(STAGING_DIR, ignore_errors=True)
```

This guarantees that the live topic directory is never in a partially-written state.

---

## config.py Additions Required

One new setting in `agent/config.py`:

```python
# Memory
memory_max_age_days: int = 7                           # already present
memory_delete_after_consolidation: bool = Field(       # NEW
    default=True, alias="MEMORY_DELETE_AFTER_CONSOLIDATION"
)
```

---

## New Model: SessionTranscript (agent/models.py)

U3 introduces one new Pydantic model (added during code generation):

```python
class SessionTranscript(BaseModel):
    """Persisted record of one agent query session."""
    session_id: str
    timestamp: float
    history: list[TraceStep]
    summary: str
```

Added to the `# Memory` section of `agent/models.py`.

---

## Filename Safety Guard (SEC-U3-02)

```python
import re
_SAFE_FILENAME_RE = re.compile(r'^[\w\-. ]+\.md$')

def inject_document(self, subdir: str, filename: str, content: str) -> None:
    if not _SAFE_FILENAME_RE.match(filename):
        raise ValueError(f"Unsafe filename: {filename!r}")
    if ".." in filename:
        raise ValueError(f"Path traversal detected in filename: {filename!r}")
    ...
```

---

## PBT Strategies Required

Six new PBT invariant properties across two test files. Hypothesis strategies needed:

| Strategy | Used For | Source |
|---|---|---|
| `correction_entries()` | PBT-U3-01, PBT-U3-02 | Already in `tests/unit/strategies.py` |
| `st.text(min_size=1, max_size=N)` | PBT-U3-03 (token gate) | Hypothesis stdlib |
| `st.uuids()` → `str()` | PBT-U3-04 (session_id) | Hypothesis stdlib |
| `session_transcripts()` | PBT-U3-05, PBT-U3-06 | New strategy in strategies.py |
| `session_memory_objects()` | PBT-U3-06 | New strategy in strategies.py |

`session_transcripts()` and `session_memory_objects()` strategies will be added to `tests/unit/strategies.py` during code generation.
