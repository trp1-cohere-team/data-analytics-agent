# Schema Introspection Tool

Converts raw schema metadata into a normalized structure for planning and retrieval.

## Purpose

Helps the agent or planner answer questions like:
- which source contains the needed entity?
- which fields exist?
- which collections contain unstructured text?

## Example

```python
from utils.schema_introspection import SchemaIntrospector

introspector = SchemaIntrospector()

sql_schema = introspector.summarize_sql_schema({
    "customers": [
        {"name": "customer_id", "data_type": "integer"},
        {"name": "segment", "data_type": "text"},
    ]
})

context = introspector.to_planner_context(sql_tables=sql_schema)
