# Business Logic Model
# U3 — Knowledge Base & Memory System

**Date**: 2026-04-11  
**Design Decisions**: Q1=D (hybrid cache), Q2=B (4k token limit), Q3=C (atomic swap),
Q4=A (dual write), Q5=A (explicit save), Q6=C (raw+summary), Q7=B (startup bg task),
Q8=C (topics + MEMORY.md), Q9=D (seed placeholder)

---

## KnowledgeBase

### 1. Initialization: `__init__(kb_dir, refresh_interval_s)`

```
self._kb_dir = Path(kb_dir)
self._refresh_interval_s = refresh_interval_s     # from config.layer2_refresh_interval_s
self._cache: dict[str, tuple[list[KBDocument], float]] = {}
self._corrections: list[CorrectionEntry] = []
self._ensure_kb_structure()
self._corrections = self._load_corrections_from_disk()
```

---

### 2. KB Structure Init: `_ensure_kb_structure()`

```
SUBDIRS = ["architecture", "domain", "evaluation", "corrections"]
CHANGELOG_HEADER = "# CHANGELOG\n\n## {subdir} Knowledge Base\n\nAppend-only log of injected documents.\n"

for subdir in SUBDIRS:
    path = self._kb_dir / subdir
    path.mkdir(parents=True, exist_ok=True)
    changelog = path / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text(CHANGELOG_HEADER.format(subdir=subdir), encoding="utf-8")
        # Q9=D: seed with minimal placeholder — no error if already exists
```

---

### 3. Document Loading: `load_documents(subdir) → list[KBDocument]`

```
# Q1=D: Hybrid — eager load with per-subdir refresh interval
now = time.monotonic()
cached_docs, loaded_at = self._cache.get(subdir, ([], 0.0))

if (now - loaded_at) < self._refresh_interval_s and cached_docs:
    return cached_docs   # cache hit — return without I/O

# Cache miss or stale — reload from disk
subdir_path = self._kb_dir / subdir
docs = []
for md_file in sorted(subdir_path.glob("*.md")):
    if md_file.name == "CHANGELOG.md":
        continue           # CHANGELOG is internal; not injected into LLM context
    content = md_file.read_text(encoding="utf-8")
    docs.append(KBDocument(
        path=str(md_file),
        content=content,
        subdirectory=subdir,
    ))

self._cache[subdir] = (docs, now)
return docs
```

---

### 4. Document Injection: `inject_document(subdir, filename, content) → None`

```
# Injection test: Q2=B — 4,000 token budget (approx: len // 4)
token_estimate = len(content) // 4
if token_estimate > 4000:
    raise ValueError(f"Document exceeds 4,000 token budget: ~{token_estimate} tokens")

# Validate UTF-8 (will raise if bytes are invalid)
content.encode("utf-8")

target = self._kb_dir / subdir / filename
target.write_text(content, encoding="utf-8")

# Append to CHANGELOG.md (append-only — KB-02)
changelog = self._kb_dir / subdir / "CHANGELOG.md"
entry = f"\n## {datetime.utcnow().isoformat()}Z\n- Injected: `{filename}` (~{token_estimate} tokens)\n"
with changelog.open("a", encoding="utf-8") as f:
    f.write(entry)

# Invalidate subdir cache so next load_documents call reloads
self._cache.pop(subdir, None)
```

---

### 5. Load Corrections: `_load_corrections_from_disk() → list[CorrectionEntry]`

```
corrections_path = self._kb_dir / "corrections" / "corrections.json"
if not corrections_path.exists():
    return []
raw = corrections_path.read_text(encoding="utf-8").strip()
if not raw:
    return []
data: list[dict] = json.loads(raw)    # JSON array (Q3=C)
return [CorrectionEntry(**item) for item in data]
```

---

### 6. Append Correction: `append_correction(entry: CorrectionEntry) → None`

```
# Q3=C: JSON array with atomic swap
# Q4=A: dual write — disk + in-memory list

corrections_path = self._kb_dir / "corrections" / "corrections.json"
tmp_path = corrections_path.with_suffix(".json.tmp")

# Build new list (existing + new entry)
all_entries = self._corrections + [entry]
serialised = json.dumps(
    [e.model_dump() for e in all_entries],
    indent=2,
    default=str,
)

# Atomic write: write tmp, then rename
tmp_path.write_text(serialised, encoding="utf-8")
tmp_path.replace(corrections_path)   # atomic on POSIX; best-effort on Windows

# Update in-memory mirror immediately (Q4=A)
self._corrections.append(entry)
```

---

### 7. Get Corrections: `get_corrections() → list[CorrectionEntry]`

```
return list(self._corrections)   # defensive copy
```

---

## MemoryManager

### 8. Initialization: `__init__(memory_dir)`

```
self._memory_dir = Path(memory_dir)
self._sessions_dir = self._memory_dir / "sessions"
self._topics_dir = self._memory_dir / "topics"
self._memory_index = self._memory_dir / "MEMORY.md"

# Create directories if not present
self._sessions_dir.mkdir(parents=True, exist_ok=True)
self._topics_dir.mkdir(parents=True, exist_ok=True)

# Bootstrap MEMORY.md index
if not self._memory_index.exists():
    self._memory_index.write_text(
        "# Memory Index\n\nAuto-generated. Do not edit manually.\n",
        encoding="utf-8",
    )

# Q7=B: launch autoDream background consolidation task at init
asyncio.get_event_loop().call_soon_threadsafe(
    lambda: asyncio.ensure_future(self._run_autoDream())
)
```

---

### 9. Save Session: `save_session(session_id, history, summary) → None`

```
# Q5=A: called explicitly by U1 Orchestrator at query end
# Q6=C: stores both raw TraceStep list and brief text summary
# KB-03: write-once — never overwrite

session_path = self._sessions_dir / f"{session_id}.json"
if session_path.exists():
    logger.warning("session_already_saved", extra={"session_id": session_id})
    return   # never overwrite

transcript = SessionTranscript(
    session_id=session_id,
    timestamp=time.time(),
    history=history,
    summary=summary,
)
session_path.write_text(
    transcript.model_dump_json(indent=2),
    encoding="utf-8",
)
```

---

### 10. Load Session: `load_session(session_id) → SessionTranscript | None`

```
session_path = self._sessions_dir / f"{session_id}.json"
if not session_path.exists():
    return None
data = json.loads(session_path.read_text(encoding="utf-8"))
return SessionTranscript(**data)
```

---

### 11. Get Topics (working memory): `get_topics() → SessionMemory`

```
def _load_json_list(path: Path) -> list:
    if not path.exists(): return []
    return json.loads(path.read_text(encoding="utf-8"))

def _load_json_dict(path: Path) -> dict:
    if not path.exists(): return {}
    return json.loads(path.read_text(encoding="utf-8"))

return SessionMemory(
    successful_patterns=_load_json_list(self._topics_dir / "successful_patterns.json"),
    user_preferences=_load_json_dict(self._topics_dir / "user_preferences.json"),
    query_corrections=_load_json_list(self._topics_dir / "query_corrections.json"),
)
```

---

### 12. autoDream: `_run_autoDream() → None`

```
# Q7=B: runs as asyncio background task at startup
# Q8=C: updates topic JSON files AND appends to MEMORY.md

cutoff = time.time() - (memory_max_age_days * 86400)   # 7 days default
stale_sessions = []

for session_file in self._sessions_dir.glob("*.json"):
    transcript = load_session(session_file.stem)
    if transcript and transcript.timestamp < cutoff:
        stale_sessions.append(transcript)

if not stale_sessions:
    return

# Merge into topic store (KB-08: additive only)
topics = get_topics()
for t in stale_sessions:
    topics = _merge_session_into_topics(t, topics)

# Write updated topic files atomically
_write_topics_atomic(topics)

# Append consolidation summary to MEMORY.md (Q8=C)
summary_block = _build_memory_md_block(stale_sessions)
with self._memory_index.open("a", encoding="utf-8") as f:
    f.write(summary_block)

logger.info("autoDream_complete", extra={"sessions_consolidated": len(stale_sessions)})
```

---

### 13. Topic Merge: `_merge_session_into_topics(transcript, topics) → SessionMemory`

```
# KB-08: additive — never delete existing topic entries

# successful_patterns: append if session summary not already in list
existing_ids = {p.get("session_id") for p in topics.successful_patterns}
if transcript.session_id not in existing_ids:
    topics.successful_patterns.append({
        "session_id": transcript.session_id,
        "timestamp": transcript.timestamp,
        "summary": transcript.summary,
    })

# user_preferences: dict.update (newer sessions overwrite on conflict)
# (preferences are inferred from session summary — stub in U3, real logic in U1)

# query_corrections: append session corrections not already present
existing_session_ids = {c.get("session_id") for c in topics.query_corrections}
if transcript.session_id not in existing_session_ids:
    topics.query_corrections.append({
        "session_id": transcript.session_id,
        "timestamp": transcript.timestamp,
    })

return topics
```

---

### 14. Atomic Topic Write: `_write_topics_atomic(topics: SessionMemory) → None`

```
# Write each topic file via .tmp → rename (same pattern as corrections.json)
for filename, data in [
    ("successful_patterns.json", topics.successful_patterns),
    ("user_preferences.json", topics.user_preferences),
    ("query_corrections.json", topics.query_corrections),
]:
    path = self._topics_dir / filename
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
```
