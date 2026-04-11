import json
import unittest
from unittest.mock import patch

from agent.data_agent.sandbox_client import SandboxClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class SandboxClientTests(unittest.TestCase):
    def test_execute_success(self) -> None:
        client = SandboxClient(base_url="http://localhost:8080", timeout_seconds=1)

        with patch(
            "agent.data_agent.sandbox_client.request.urlopen",
            return_value=_FakeHTTPResponse(
                {
                    "result": {"rows": [{"ok": 1}]},
                    "trace": ["ok"],
                    "validation_status": "passed",
                    "error_if_any": None,
                }
            ),
        ):
            result = client.execute({"mode": "duckdb_sql", "sql": "SELECT 1;", "db_path": "/tmp/a.duckdb"})

        self.assertTrue(result.success)
        self.assertEqual(result.endpoint, "/execute")
        assert result.response is not None
        self.assertEqual(result.response.get("validation_status"), "passed")

    def test_execute_validation_failure(self) -> None:
        client = SandboxClient(base_url="http://localhost:8080", timeout_seconds=1)

        with patch(
            "agent.data_agent.sandbox_client.request.urlopen",
            return_value=_FakeHTTPResponse(
                {
                    "result": None,
                    "trace": ["validation_failed"],
                    "validation_status": "failed",
                    "error_if_any": "mutating sql blocked",
                }
            ),
        ):
            result = client.execute({"mode": "duckdb_sql", "sql": "DROP TABLE x;", "db_path": "/tmp/a.duckdb"})

        self.assertFalse(result.success)
        self.assertIn("mutating sql blocked", str(result.error))


if __name__ == "__main__":
    unittest.main()
