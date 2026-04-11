from utils.schema_introspection import SchemaIntrospector


def test_summarize_sql_schema() -> None:
    introspector = SchemaIntrospector()
    raw = {
        "customers": [
            {"name": "customer_id", "data_type": "integer"},
            {"name": "segment", "data_type": "text"},
        ]
    }

    result = introspector.summarize_sql_schema(raw)

    assert len(result) == 1
    assert result[0].name == "customers"
    assert result[0].columns[0].name == "customer_id"


def test_summarize_document_schema() -> None:
    introspector = SchemaIntrospector()
    raw = {
        "tickets": ["ticket_id", "customer_id", "support_notes"],
    }

    result = introspector.summarize_document_schema(raw)

    assert result["tickets"] == ["customer_id", "support_notes", "ticket_id"]


def test_to_planner_context() -> None:
    introspector = SchemaIntrospector()
    sql = introspector.summarize_sql_schema(
        {
            "orders": [
                {"name": "order_id", "data_type": "integer"},
            ]
        }
    )
    docs = introspector.summarize_document_schema(
        {
            "reviews": ["review_text", "customer_id"],
        }
    )

    result = introspector.to_planner_context(sql_tables=sql, document_collections=docs)

    assert result["sql_tables"][0]["name"] == "orders"
    assert "reviews" in result["document_collections"]
