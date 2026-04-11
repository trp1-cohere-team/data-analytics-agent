# NFR Design Patterns
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11  
**NFR Design Decisions**: Q1=A (asyncio.to_thread), Q2=A (wipe stale staging), Q3=B (instance-level lock)

---

## Pattern 1: AsyncFileIOWrapper

**Addresses**: Q1=A — all disk I/O non-blocking on event loop

**Problem**: `KnowledgeBase` and `MemoryManager` are called from U1's async request handlers running on the asyncio event loop. `Path.read_text`, `Path.write_text`, and `Path.replace` are synchronous blocking calls. Under load (concurrent queries), a slow disk or large file read would stall the event loop for all in-flight requests.

**Solution**: Wrap every disk I/O call in `asyncio.to_thread()`, offloading it to the default `ThreadPoolExecutor`. The event loop remains free to handle other coroutines while disk I/O completes on a worker thread.

**Implementation**:
```python
import asyncio
from pathlib import Path

async def _read_text(path: Path, encoding: str = "utf-8") -> str:
    return await asyncio.to_thread(path.read_text, encoding=encoding)

async def _write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    await asyncio.to_thread(path.write_text, content, encoding=encoding)

async def _replace_file(src: Path, dst: Path) -> None:
    await asyncio.to_thread(src.replace, dst)

async def _mkdir(path: Path) -> None:
    await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)

async def _glob(path: Path, pattern: str) -> list[Path]:
    return await asyncio.to_thread(lambda: sorted(path.glob(pattern)))
```

These five helpers are defined as module-level functions in both `knowledge_base.py` and `memory/manager.py` (no shared module needed — they're trivially small).

**Tradeoffs**:
- Each `to_thread` call submits to the default thread pool (default size: `min(32, cpu_count+4)`). For local SSD I/O this is essentially free overhead.
- Thread pool shared with other `to_thread` callers in the process. No starvation risk at single-agent scale.
- Makes all public KnowledgeBase and MemoryManager methods `async` — callers use `await`.

---

## Pattern 2: StagingTransactionWriter

**Addresses**: REL-U3-01 (full rollback on partial failure), Q2=A (wipe stale staging)

**Problem**: autoDream must update three topic JSON files atomically. If the process crashes after writing `successful_patterns.json` but before writing `query_corrections.json`, the topic store is in an inconsistent state — some sessions appear consolidated but the correction index has not been updated.

**Solution**: Write all three files to a `.staging/` subdirectory first. Only after all three staging writes succeed does the code perform the atomic renames to the final locations. On failure at any point, the staging directory is wiped — originals are untouched.

At autoDream start, any leftover `.staging/` from a prior failed run is wiped (Q2=A — fresh start):

**Implementation**:
```python
STAGING = self._topics_dir / ".staging"

# Step 0: Wipe any stale staging from prior crash (Q2=A)
if STAGING.exists():
    await asyncio.to_thread(shutil.rmtree, STAGING, True)

await _mkdir(STAGING)
try:
    # Step 1: Write all three to staging
    for filename, data in [
        ("successful_patterns.json", topics.successful_patterns),
        ("user_preferences.json",    topics.user_preferences),
        ("query_corrections.json",   topics.query_corrections),
    ]:
        content = json.dumps(data, indent=2, default=str)
        await _write_text(STAGING / filename, content)

    # Step 2: All staging writes succeeded — atomic renames
    for filename in ("successful_patterns.json", "user_preferences.json", "query_corrections.json"):
        await _replace_file(STAGING / filename, self._topics_dir / filename)

finally:
    # Step 3: Clean staging regardless of success or failure
    await asyncio.to_thread(shutil.rmtree, STAGING, True)
```

**Invariant**: After `_write_topics_atomic` returns (success or exception), `.staging/` does not exist and the topic files are either all updated or all unchanged.

---

## Pattern 3: InstanceScopedLockRegistry

**Addresses**: CONC-U3-01 (corrections write), CONC-U3-02 (session save), Q3=B (instance-level)

**Problem**: Two concurrent coroutines calling `append_correction` on the same `KnowledgeBase` instance perform a read-modify-write on `corrections.json`. Without synchronization, one update can overwrite the other's appended entry.

**Solution**: Each `KnowledgeBase` instance holds its own `asyncio.Lock` (`self._corrections_lock`). Each `MemoryManager` instance holds a `dict[str, asyncio.Lock]` for per-session-id locking. Locks are instance-level (Q3=B) — test code can instantiate multiple independent instances without lock interference.

**Implementation**:

```python
# KnowledgeBase.__init__
self._corrections_lock = asyncio.Lock()

# KnowledgeBase.append_correction
async def append_correction(self, entry: CorrectionEntry) -> None:
    async with self._corrections_lock:
        all_entries = list(self._corrections) + [entry]
        content = json.dumps([e.model_dump() for e in all_entries], indent=2, default=str)
        tmp = self._corrections_path.with_suffix(".json.tmp")
        await _write_text(tmp, content)
        await _replace_file(tmp, self._corrections_path)
        self._corrections.append(entry)   # update mirror after disk succeeds

# MemoryManager.__init__
self._session_locks: dict[str, asyncio.Lock] = {}

# MemoryManager.save_session
async def save_session(self, session_id: str, ...) -> None:
    if session_id not in self._session_locks:
        self._session_locks[session_id] = asyncio.Lock()
    async with self._session_locks[session_id]:
        session_path = self._sessions_dir / f"{session_id}.json"
        exists = await asyncio.to_thread(session_path.exists)
        if exists:
            logger.warning("session_already_exists", extra={"session_id": session_id})
            return
        # write...
```

**Why instance-level over module-level**: In tests, each test creates a fresh `KnowledgeBase(tmp_dir)`. With a module-level lock, concurrent tests would serialize against each other even though they use separate directories. Instance-level locks give full parallelism in the test suite.

---

## Pattern 4: StructuredMemoryLogger

**Addresses**: OBS-U3-01 through OBS-U3-05, SEC-U3-01 (no content in logs)

**Problem**: Ad-hoc `print()` or unstructured logging makes it impossible to grep for specific session IDs or correlate consolidation events across agent restarts. OBS-U3-04 forbids logging query or session content.

**Solution**: Named log events with consistent `extra` field schema. Two logger instances — one per component — with all events defined as typed helper calls that enforce the schema.

**Implementation** (illustrative — implemented as standalone functions, not a class):

```python
# knowledge_base.py
_kb_logger = logging.getLogger("agent.kb")

def _log_documents_loaded(subdir: str, doc_count: int, from_cache: bool, elapsed_ms: float) -> None:
    _kb_logger.info("documents_loaded", extra={
        "subdir": subdir, "doc_count": doc_count,
        "from_cache": from_cache, "elapsed_ms": round(elapsed_ms, 1),
    })

def _log_correction_appended(entry_id: str, failure_type: str, total_count: int) -> None:
    _kb_logger.info("correction_appended", extra={
        "entry_id": entry_id, "failure_type": failure_type, "total_count": total_count,
    })

# memory/manager.py
_mem_logger = logging.getLogger("agent.memory")

def _log_session_saved(session_id: str, trace_steps: int, elapsed_ms: float) -> None:
    _mem_logger.info("session_saved", extra={
        "session_id": session_id, "trace_steps": trace_steps,
        "elapsed_ms": round(elapsed_ms, 1),
    })

def _log_autodream_complete(consolidated: int, deleted: int, elapsed_ms: float) -> None:
    _mem_logger.info("autodream_complete", extra={
        "sessions_consolidated": consolidated,
        "sessions_deleted": deleted,
        "elapsed_ms": round(elapsed_ms, 1),
    })
```

No log event ever includes: query text, correction content, session summary text, or file content. Only counts, IDs, types, and timings (OBS-U3-04, SEC-U3-01).
