
# 3. `utils/schema_introspection/`

## `utils/schema_introspection/introspect.py`


from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: list[ColumnInfo]


class SchemaIntrospector:
    """
    Normalizes raw schema metadata into a planner-friendly structure.
    """

    def summarize_sql_schema(self, raw_schema: dict[str, list[dict[str, str]]]) -> list[TableInfo]:
        summary: list[TableInfo] = []

        for table_name, columns in raw_schema.items():
            summary.append(
                TableInfo(
                    name=table_name,
                    columns=[
                        ColumnInfo(
                            name=col["name"],
                            data_type=col["data_type"],
                        )
                        for col in columns
                    ],
                )
            )

        return summary

    def summarize_document_schema(self, raw_schema: dict[str, list[str]]) -> dict[str, list[str]]:
        return {
            collection_name: sorted(fields)
            for collection_name, fields in raw_schema.items()
        }

    def to_planner_context(
        self,
        sql_tables: list[TableInfo] | None = None,
        document_collections: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "sql_tables": [
                {
                    "name": table.name,
                    "columns": [
                        {"name": column.name, "data_type": column.data_type}
                        for column in table.columns
                    ],
                }
                for table in (sql_tables or [])
            ],
            "document_collections": document_collections or {},
        }
