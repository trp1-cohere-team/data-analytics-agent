# Utils — Shared Utility Library

Four pure-utility modules shared across agent units. No side effects, no global state mutation.

---

## 1. `schema_introspector.py`

**Purpose:** Auto-introspects all 4 database schemas via MCP Toolbox using a bulkhead
timeout pattern. Partial failures return empty `DBSchema` with an error field — never
block agent startup.

**Key functions / classes:**
- `AiohttpMCPClient` — async HTTP client for MCP Toolbox
- `introspect_all(client)` → `SchemaContext` — runs all 4 DB introspections in parallel
- `SchemaIntrospector(base_url)` — wrapper with configurable per-DB timeouts

**Timeout configuration (seconds):**
| Database | Timeout |
|----------|---------|
| MongoDB | 4.0 |
| PostgreSQL | 2.5 |
| DuckDB | 1.5 |
| SQLite | 1.0 |
| Outer ceiling | 9.0 |

**Usage example:**
```python
import asyncio
from utils.schema_introspector import AiohttpMCPClient, introspect_all

async def main():
    client = AiohttpMCPClient("http://localhost:5000")
    schema = await introspect_all(client=client)
    for db_name, db in schema.databases.items():
        print(f"{db_name}: {[t.name for t in db.tables]}")

asyncio.run(main())
```

**Tests:** `tests/unit/test_schema_introspector.py`, `tests/integration/test_schema_introspection_live.py`

---

## 2. `join_key_utils.py`

**Purpose:** Cross-database join key format detection and transformation. All functions are pure.

**Key functions:**
- `JoinKeyUtils.detect_format(value)` → `JoinKeyFormat` — detect INTEGER / PREFIXED_STRING / UUID / COMPOSITE
- `JoinKeyUtils.transform_key(value, source_fmt, target_fmt, width)` → `str | None` — convert between formats
- `JoinKeyUtils.build_transform_expression(source_column, source_format, target_format, db_type)` → `str` — SQL expression for in-query transformation

**Supported transformations:**
| From | To | Example |
|------|----|---------|
| INTEGER | PREFIXED_STRING | `42` → `ORD-0042` |
| PREFIXED_STRING | INTEGER | `ORD-0042` → `42` |
| PREFIXED_STRING | PREFIXED_STRING (re-pad) | `ORD-42` → `ORD-0042` |
| INTEGER | UUID | `42` → `00000000-...-0042` |

**Usage example:**
```python
from utils.join_key_utils import JoinKeyUtils
from agent.models import JoinKeyFormat

expr = JoinKeyUtils.build_transform_expression(
    source_column="order_id",
    source_format=JoinKeyFormat.INTEGER,
    target_format=JoinKeyFormat.PREFIXED_STRING,
    db_type="postgres",
)
# Returns: "CONCAT('ORD-', LPAD(CAST(order_id AS TEXT), 5, '0'))"
```

**Tests:** `tests/unit/test_join_key_utils.py`

---

## 3. `multi_pass_retriever.py`

**Purpose:** 3-vocabulary-pass keyword search over the corrections log. Scores entries
using static tiers + IDF multiplier (corpus ≥ 20 entries), deduplicates, returns top 10.

**Key functions:**
- `MultiPassRetriever.retrieve(query, entries)` → `list[CorrectionEntry]` — retrieve top-10 relevant corrections

**IDF formula:** `log((n+1) / (df+1))` — always ≥ 0, smoothed for full-corpus terms.

**Usage example:**
```python
from utils.multi_pass_retriever import MultiPassRetriever
from agent.models import CorrectionEntry

retriever = MultiPassRetriever()
entries = [CorrectionEntry(query="...", correction="...", ...)]
top = retriever.retrieve("ROWNUM syntax error", entries)
```

**Tests:** `tests/unit/test_multi_pass_retriever.py`

---

## 4. `benchmark_wrapper.py`

**Purpose:** Simplified Python API for running DAB query subsets. Delegates all scoring
and tracing to `EvaluationHarness` (eval/harness.py).

**Key functions:**
- `load_dab_queries(path)` → `list[DABQuery]` — load benchmark queries from JSON file
- `BenchmarkWrapper.run_subset(queries, n_trials)` → `BenchmarkResult` — run eval on subset

**Usage example:**
```python
import asyncio
from utils.benchmark_wrapper import BenchmarkWrapper, load_dab_queries

queries = load_dab_queries("eval/test_set.json")
wrapper = BenchmarkWrapper()
result = asyncio.run(wrapper.run_subset(queries[:5], n_trials=3))
print(f"Mean score: {result.mean_score:.3f}")
```

**Tests:** `tests/unit/test_scorers.py`, `tests/unit/test_harness.py`
