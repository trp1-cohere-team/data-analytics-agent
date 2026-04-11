# Tech Stack Decisions
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes

---

## Decision Table

| Concern | Decision | Library / Tool | Rationale |
|---|---|---|---|
| Language | Python 3.11+ | — | Project-wide decision |
| HTTP client (SchemaIntrospector) | `aiohttp` | `aiohttp>=3.9` | Async; consistent with U2 MultiDBEngine; already in requirements |
| Format detection (JoinKeyUtils) | Standard library `re` | `re` (stdlib) | Pure regex; no external dependency; zero overhead |
| PBT framework | `hypothesis` | `hypothesis>=6.100` | Mandatory (blocking extension); best-in-class property-based testing for Python |
| PBT custom strategies | `hypothesis.strategies` | `hypothesis` | `@st.composite` decorators for JoinKeyFormat value generators |
| Unit testing | `pytest` | `pytest>=8.0` | Project-wide decision |
| Async test support | `pytest-asyncio` | `pytest-asyncio>=0.23` | Required for SchemaIntrospector async tests |
| Type checking | `mypy` | `mypy>=1.9` | Strict mode; catches `None` return paths in JoinKeyUtils |
| Dataclasses | `dataclasses` (stdlib) | stdlib | JoinKeyFormatResult, KeywordScore — no Pydantic needed (internal-only) |
| Shared models | `pydantic` v2 | `pydantic>=2.6` | DBSchema, SchemaContext, CorrectionEntry (shared with all units via agent/models.py) |

---

## Decision Detail

### aiohttp for SchemaIntrospector
SchemaIntrospector makes async HTTP calls to MCP Toolbox. `aiohttp` is chosen (not `httpx`) because:
- U2 MultiDBEngine already uses `aiohttp` for MCP Toolbox calls — single HTTP client library across both units
- Native `asyncio` integration
- `asyncio.wait_for` works directly with `aiohttp` session calls for the 10s total timeout

Timeout implementation:
```python
async with asyncio.timeout(10):  # Python 3.11+ syntax
    results = await asyncio.gather(
        introspect_postgres(db_name),
        introspect_sqlite(db_path),
        introspect_mongodb(db_name),
        introspect_duckdb(db_path),
        return_exceptions=True   # partial failure → empty DBSchema, not exception
    )
```

### `re` for JoinKeyUtils Format Detection
`_classify_single` uses 3 compiled regex patterns:
```python
_DIGITS_RE     = re.compile(r'^\d+$')
_PREFIXED_RE   = re.compile(r'^[A-Z][A-Z0-9]*-\d+$')
_UUID_RE       = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
```
Patterns are module-level constants (compiled once at import). No external library needed.

### `hypothesis` for PBT
Five property tests (PBT-U5-01 through PBT-U5-05) require custom Hypothesis strategies:

```python
@st.composite
def integer_keys(draw):
    return draw(st.integers(min_value=1, max_value=999999))

@st.composite
def prefixed_keys(draw, prefix="CUST", width=5):
    n = draw(st.integers(min_value=0, max_value=10**width - 1))
    return f"{prefix}-{str(n).zfill(width)}"

@st.composite
def uuid_keys(draw):
    return str(draw(st.uuids()))
```

Hypothesis settings: `max_examples=200` for round-trip tests; `max_examples=100` for monotonicity.

### stdlib `dataclasses` for Internal Entities
`JoinKeyFormatResult` and `KeywordScore` are used only within U5. Using `@dataclass` (stdlib) avoids Pydantic overhead for structures that never cross API or serialization boundaries. `frozen=True` enforced for `JoinKeyFormatResult` (immutable result object).

### Pydantic v2 for Shared Models
`DBSchema`, `SchemaContext`, `CorrectionEntry`, `ProbeEntry` are defined in `agent/models.py` (shared infrastructure) using Pydantic v2 `BaseModel`. These cross unit boundaries and require validation, serialization, and JSON compatibility.

---

## Libraries NOT Used (and Why)

| Library | Rejected | Reason |
|---|---|---|
| `sqlglot` | No | SQL expression validation for PBT-U5-05 is a lightweight regex check, not a full parse. sqlglot would add significant dependency weight for minimal benefit. |
| `nltk` / `spacy` | No | MultiPassRetriever Pass 3 domain term extraction uses heuristic rules (word length, snake_case), not NLP. NLP libraries are overkill for a 50-entry corrections corpus. |
| `httpx` | No | aiohttp already chosen for U2; consistency over variety |
| `scikit-learn` | No | IDF is computed with a simple log formula over 50 entries; no ML library needed |

---

## Dependencies Added to requirements.txt

```
# U5 specific additions (others already present from project baseline)
hypothesis>=6.100.0
pytest-asyncio>=0.23.0
```

All other U5 dependencies (`aiohttp`, `pydantic`, `pytest`, `mypy`) are already in the project baseline from U1/U2 requirements.
