# Domain Entities
# U5 — Utilities & Adversarial Probes

**Date**: 2026-04-11  
**Unit**: U5 — Utilities & Adversarial Probes  
**Note**: All entities defined here are shared via `agent/models.py`. Technology-agnostic (no ORM, no DB schema).

---

## Entity 1: JoinKeyFormat (Enum)

**Purpose**: Identifies the structural format of a database join key column.

| Value | Description | Example Values |
|---|---|---|
| `INTEGER` | Numeric integer key | `1234`, `99`, `0` |
| `PREFIXED_STRING` | Uppercase prefix + hyphen + digits | `"CUST-01234"`, `"ORD-007"`, `"ITEM-9"` |
| `UUID` | Standard UUID v4 format | `"550e8400-e29b-41d4-a716-446655440000"` |
| `COMPOSITE` | Multi-field or delimited composite key | `(1, "US")`, `"1234::USD"`, `[99, "A"]` |
| `UNKNOWN` | Cannot be classified | Any value not matching above patterns |

---

## Entity 2: JoinKeyFormatResult (Dataclass)

**Purpose**: Result of multi-sample format detection. Carries the dominant format and any minority formats observed.

| Field | Type | Required | Description |
|---|---|---|---|
| `primary_format` | `JoinKeyFormat` | Yes | Format detected in majority of samples |
| `secondary_formats` | `list[JoinKeyFormat]` | Yes | Other formats seen in minority of samples (never includes UNKNOWN) |

**Invariants**:
- `primary_format` is always set (never None)
- `secondary_formats` never contains `UNKNOWN`
- `secondary_formats` never contains `primary_format`
- `secondary_formats` is empty list (not None) when no minority formats exist

---

## Entity 3: ColumnSchema (Dataclass)

**Purpose**: Metadata for one column/field within a table or collection.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Column or field name |
| `data_type` | `str` | Yes | DB-native type string (e.g. `"integer"`, `"text"`, `"double"`, `"ObjectId"`) |
| `nullable` | `bool` | Yes | Whether the column can contain NULL/None |
| `is_primary_key` | `bool` | Yes | Whether this column is part of the primary key |

---

## Entity 4: ForeignKeyRelationship (Dataclass)

**Purpose**: Represents a FK constraint or inferred relationship between two columns.

| Field | Type | Required | Description |
|---|---|---|---|
| `from_table` | `str` | Yes | Table containing the FK column |
| `from_column` | `str` | Yes | FK column name |
| `to_table` | `str` | Yes | Referenced table |
| `to_column` | `str` | Yes | Referenced column |

---

## Entity 5: TableSchema (Dataclass)

**Purpose**: Full schema metadata for one table or MongoDB collection.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Table or collection name |
| `columns` | `list[ColumnSchema]` | Yes | All columns/fields (empty list if introspection failed) |
| `foreign_keys` | `list[ForeignKeyRelationship]` | Yes | FK relationships from this table (empty for MongoDB) |

---

## Entity 6: DBSchema (Dataclass)

**Purpose**: Complete schema for one database or MongoDB database.

| Field | Type | Required | Description |
|---|---|---|---|
| `db_name` | `str` | Yes | Database name or path |
| `db_type` | `str` | Yes | One of: `"postgres"`, `"sqlite"`, `"mongodb"`, `"duckdb"` |
| `tables` | `list[TableSchema]` | Yes | All tables/collections (empty list on error) |
| `error` | `str \| None` | No | Set to error description if introspection failed; None on success |

---

## Entity 7: SchemaContext (Dataclass)

**Purpose**: Aggregated schema for all connected databases. This is Layer 1 of the context bundle.

| Field | Type | Required | Description |
|---|---|---|---|
| `databases` | `dict[str, DBSchema]` | Yes | Key = db_name, Value = DBSchema. Empty dict if all introspections failed. |
| `loaded_at` | `datetime` | Yes | Timestamp when introspection completed (for cache staleness detection) |

---

## Entity 8: CorrectionEntry (Dataclass)

**Purpose**: One record in the corrections log. Written by CorrectionEngine; read by MultiPassRetriever and ContextManager.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | Yes | Unique identifier (UUID) |
| `timestamp` | `float` | Yes | Unix timestamp (seconds since epoch) |
| `session_id` | `str` | Yes | Session in which correction occurred |
| `failure_type` | `str` | Yes | One of: `SYNTAX_ERROR`, `JOIN_KEY_MISMATCH`, `WRONG_DB_TYPE`, `DATA_QUALITY`, `UNKNOWN` |
| `original_query` | `str` | Yes | The query that failed |
| `corrected_query` | `str \| None` | No | The corrected query (None if correction failed) |
| `error_message` | `str` | Yes | Raw error from the DB driver |
| `fix_strategy` | `str` | Yes | Which fix was applied: `rule_syntax`, `rule_join_key`, `rule_db_type`, `rule_null_guard`, `llm_corrector` |
| `attempt_number` | `int` | Yes | 1, 2, or 3 |
| `success` | `bool` | Yes | Whether the corrected query succeeded |

---

## Entity 9: ProbeEntry (Dataclass)

**Purpose**: One adversarial probe definition + recorded results. Stored in `probes/probes.md` (Markdown table format) and loaded by ProbeRunner.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | Yes | Unique probe ID. Format: `{CATEGORY}-{NNN}` e.g. `ROUTING-001` |
| `category` | `str` | Yes | One of: `ROUTING`, `JOIN_KEY`, `TEXT_EXTRACT`, `DOMAIN_GAP` |
| `query` | `str` | Yes | The adversarial natural language question |
| `description` | `str` | Yes | Why this probe is adversarial — what failure it is designed to trigger |
| `expected_failure_mode` | `str` | Yes | Human-readable description of the expected pre-fix failure |
| `db_types_involved` | `list[str]` | Yes | Which DB types this probe exercises (e.g. `["postgres", "mongodb"]`) |
| `fix_applied` | `str` | Yes | Description of the fix applied to the agent (KB update, correction rule, etc.) |
| `error_signal` | `str \| None` | No | Exact error text from query trace that triggered correction (recorded by ProbeRunner) |
| `correction_attempt_count` | `int \| None` | No | Number of correction attempts before success/failure (from trace) |
| `observed_agent_response` | `str \| None` | No | Pre-fix agent answer (recorded by ProbeRunner) |
| `pre_fix_score` | `float \| None` | No | Score before fix (0.0–1.0); None until ProbeRunner records it |
| `post_fix_score` | `float \| None` | No | Score after fix (0.0–1.0); None until ProbeRunner records it |
| `post_fix_pass` | `bool \| None` | No | `True` if `post_fix_score >= 0.8`; None until ProbeRunner records it |

---

## Entity 10: KeywordScore (Internal — MultiPassRetriever only)

**Purpose**: Intermediate scoring structure used during `retrieve_corrections`. Not persisted, not exported.

| Field | Type | Description |
|---|---|---|
| `entry_id` | `str` | CorrectionEntry.id |
| `raw_score` | `float` | Sum of (tier_score × idf_multiplier) across all matching keywords |
| `timestamp` | `float` | CorrectionEntry.timestamp (for tiebreaking) |
| `entry` | `CorrectionEntry` | Reference to the original entry |

---

## Entity Relationship Summary

```
SchemaContext
  └── dict[db_name → DBSchema]
        └── list[TableSchema]
              ├── list[ColumnSchema]
              └── list[ForeignKeyRelationship]

JoinKeyFormatResult
  ├── primary_format: JoinKeyFormat (enum)
  └── secondary_formats: list[JoinKeyFormat]

CorrectionEntry  ←──── written by CorrectionEngine (U1)
                  ←──── read by MultiPassRetriever (U5)
                  ←──── read by ContextManager Layer 3 (U1)

ProbeEntry       ←──── defined in probes/probes.md (static)
                  ←──── populated at runtime by ProbeRunner
```
