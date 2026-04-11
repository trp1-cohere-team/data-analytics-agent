import os
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

from agent.data_agent.mcp_toolbox_client import MCPInvocationResult
from agent.data_agent.sandbox_client import SandboxExecutionResult
from agent.runtime.tooling import ToolPolicy, ToolRegistry
from agent.runtime.worker import QueryWorker


class _FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_tool(self, tool_name: str, tool_input: dict[str, Any]) -> MCPInvocationResult:
        self.calls.append((tool_name, tool_input))
        return MCPInvocationResult(
            success=True,
            endpoint=f"/v1/tools/{tool_name}:invoke",
            request_body={"input": tool_input},
            response={"rows": []},
        )


class _FakeMCPClientQualifierFailure:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_tool(self, tool_name: str, tool_input: dict[str, Any]) -> MCPInvocationResult:
        self.calls.append((tool_name, tool_input))
        sql = str(tool_input.get("sql", ""))
        if "bookreview_db." in sql:
            return MCPInvocationResult(
                success=True,
                endpoint=f"/v1/tools/{tool_name}:invoke",
                request_body={"input": tool_input},
                response={
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": 'ERROR: relation "bookreview_db.books" does not exist',
                        }
                    ],
                },
            )
        return MCPInvocationResult(
            success=True,
            endpoint=f"/v1/tools/{tool_name}:invoke",
            request_body={"input": tool_input},
            response={"rows": [{"book_id": 1}]},
        )


class _FakeMCPClientMissingTable:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_tool(self, tool_name: str, tool_input: dict[str, Any]) -> MCPInvocationResult:
        self.calls.append((tool_name, tool_input))
        sql = str(tool_input.get("sql", ""))
        if "books_info" in sql:
            return MCPInvocationResult(
                success=True,
                endpoint=f"/v1/tools/{tool_name}:invoke",
                request_body={"input": tool_input},
                response={"rows": [{"book_id": 1}]},
            )
        return MCPInvocationResult(
            success=True,
            endpoint=f"/v1/tools/{tool_name}:invoke",
            request_body={"input": tool_input},
            response={
                "isError": True,
                "content": [{"type": "text", "text": 'ERROR: relation "books" does not exist'}],
            },
        )


class _FakeClient:
    enabled = False


class _FakeSandboxClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, payload: dict[str, Any]) -> SandboxExecutionResult:
        self.calls.append(payload)
        return SandboxExecutionResult(
            success=True,
            endpoint="/execute",
            request_body=payload,
            response={"result": {"rows": [{"ok": 1}], "columns": ["ok"], "row_count": 1}},
        )


class WorkerTests(unittest.TestCase):
    def test_worker_executes_step_with_query_input(self) -> None:
        mcp_client = _FakeMCPClient()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=0,
        )
        registry = ToolRegistry(["postgres_query"])

        events: list[dict[str, Any]] = []

        record = worker.execute_step(
            question="Show recent orders",
            step={
                "database": "sales_pg",
                "db_type": "postgresql",
                "tool": "postgres_query",
                "input": {"query": "SELECT * FROM orders LIMIT 5;"},
            },
            registry=registry,
            emit_trace=lambda **kwargs: events.append(kwargs),
            record_correction=lambda **kwargs: None,
        )

        self.assertTrue(record["success"])
        self.assertEqual(len(mcp_client.calls), 1)
        self.assertEqual(mcp_client.calls[0][0], "postgres_query")
        self.assertEqual(
            mcp_client.calls[0][1]["query"],
            "SELECT * FROM orders LIMIT 5;",
        )
        self.assertTrue(any(evt.get("stage") == "worker_step_started" for evt in events))

    def test_worker_executes_duckdb_step_locally_when_mcp_tool_missing(self) -> None:
        mcp_client = _FakeMCPClient()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=0,
        )
        registry = ToolRegistry(["postgres_query", "sqlite_query", "mongo_aggregate"])

        with patch.object(
            worker,
            "_invoke_duckdb_local",
            return_value=MCPInvocationResult(
                success=True,
                endpoint="local://duckdb",
                request_body={"sql": "SELECT 1 AS ok;"},
                response={"rows": [{"ok": 1}]},
            ),
        ):
            record = worker.execute_step(
                question="Run a quick duckdb check",
                step={
                    "database": "warehouse_duck",
                    "db_type": "duckdb",
                    "tool": "duckdb_query",
                    "input": {"query": "SELECT 1 AS ok;"},
                },
                registry=registry,
                emit_trace=lambda **kwargs: None,
                record_correction=lambda **kwargs: None,
            )

        self.assertTrue(record["success"])
        self.assertEqual(record["endpoint"], "local://duckdb")
        self.assertEqual(len(mcp_client.calls), 0)

    def test_worker_routes_duckdb_local_execution_via_sandbox_when_enabled(self) -> None:
        mcp_client = _FakeMCPClient()
        sandbox_client = _FakeSandboxClient()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            sandbox_client=sandbox_client,
            use_sandbox=True,
            self_correction_retries=0,
        )
        registry = ToolRegistry(["postgres_query", "sqlite_query", "mongo_aggregate"])

        record = worker.execute_step(
            question="Run a quick duckdb check",
            step={
                "database": "warehouse_duck",
                "db_type": "duckdb",
                "tool": "duckdb_query",
                "input": {"query": "SELECT 1 AS ok;"},
            },
            registry=registry,
            emit_trace=lambda **kwargs: None,
            record_correction=lambda **kwargs: None,
        )

        self.assertTrue(record["success"])
        self.assertEqual(record["endpoint"], "sandbox://execute")
        self.assertEqual(len(mcp_client.calls), 0)
        self.assertEqual(len(sandbox_client.calls), 1)
        self.assertEqual(sandbox_client.calls[0]["mode"], "duckdb_sql")
        self.assertIn("SELECT 1 AS ok", sandbox_client.calls[0]["sql"])

    def test_worker_blocks_mutating_duckdb_sql_in_local_mode(self) -> None:
        mcp_client = _FakeMCPClient()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=0,
        )
        registry = ToolRegistry(["postgres_query", "sqlite_query", "mongo_aggregate"])

        record = worker.execute_step(
            question="Drop a table",
            step={
                "database": "warehouse_duck",
                "db_type": "duckdb",
                "tool": "duckdb_query",
                "input": {"query": "DROP TABLE customers;"},
            },
            registry=registry,
            emit_trace=lambda **kwargs: None,
            record_correction=lambda **kwargs: None,
        )

        self.assertFalse(record["success"])
        self.assertTrue(record.get("policy_blocked", False))
        self.assertEqual(len(mcp_client.calls), 0)

    def test_invoke_duckdb_local_success_includes_db_path(self) -> None:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            self.skipTest("duckdb not installed")

        mcp_client = _FakeMCPClient()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sample.duckdb")
            duck_conn = duckdb.connect(db_path)
            duck_conn.execute("CREATE TABLE sample (ok INTEGER)")
            duck_conn.execute("INSERT INTO sample VALUES (1)")
            duck_conn.close()

            result = worker._invoke_duckdb_local(
                tool_input={"sql": "SELECT ok FROM sample", "db_path": db_path}
            )

        self.assertTrue(result.success)
        self.assertEqual(result.request_body["db_path"], db_path)
        self.assertEqual(result.response["rows"], [{"ok": 1}])

    def test_worker_rule_based_retry_fixes_db_qualifier_errors(self) -> None:
        mcp_client = _FakeMCPClientQualifierFailure()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=1,
        )
        registry = ToolRegistry(["postgres_query"])

        record = worker.execute_step(
            question="Get rated books by decade",
            step={
                "database": "books_database",
                "db_type": "postgresql",
                "tool": "postgres_query",
                "input": {"query": "SELECT * FROM bookreview_db.books LIMIT 5;"},
            },
            registry=registry,
            emit_trace=lambda **kwargs: None,
            record_correction=lambda **kwargs: None,
        )

        self.assertTrue(record["success"])
        self.assertTrue(record.get("corrected", False))
        self.assertEqual(len(mcp_client.calls), 2)
        self.assertIn("bookreview_db.", mcp_client.calls[0][1].get("sql", ""))
        self.assertNotIn("bookreview_db.", mcp_client.calls[1][1].get("sql", ""))

    def test_worker_rule_based_retry_maps_missing_table_to_known_object(self) -> None:
        mcp_client = _FakeMCPClientMissingTable()
        worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=ToolPolicy(),
            client=_FakeClient(),
            self_correction_retries=1,
        )
        registry = ToolRegistry(["postgres_query"])

        record = worker.execute_step(
            question="Find books",
            step={
                "database": "books_database",
                "db_type": "postgresql",
                "tool": "postgres_query",
                "input": {"query": "SELECT * FROM books LIMIT 5;"},
                "known_objects": ["books_info", "authors"],
            },
            registry=registry,
            emit_trace=lambda **kwargs: None,
            record_correction=lambda **kwargs: None,
        )

        self.assertTrue(record["success"])
        self.assertTrue(record.get("corrected", False))
        self.assertEqual(len(mcp_client.calls), 2)
        self.assertIn("FROM books", mcp_client.calls[0][1].get("sql", ""))
        self.assertIn("FROM books_info", mcp_client.calls[1][1].get("sql", ""))


if __name__ == "__main__":
    unittest.main()
