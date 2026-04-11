from __future__ import annotations

import ast
import json
import multiprocessing as mp
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MUTATING_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
    flags=re.IGNORECASE,
)


def _allowed_roots() -> list[Path]:
    raw = os.getenv("SANDBOX_ALLOWED_ROOTS", "")
    if not raw.strip():
        return [Path.cwd().resolve(), Path("/tmp").resolve()]
    roots: list[Path] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        roots.append(Path(value).resolve())
    return roots or [Path.cwd().resolve(), Path("/tmp").resolve()]


def _is_path_allowed(path: str) -> bool:
    resolved = Path(path).resolve()
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _validate_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "Payload must be a JSON object"

    encoded = json.dumps(payload, ensure_ascii=False)
    max_chars = int(os.getenv("SANDBOX_MAX_PAYLOAD_CHARS", "50000"))
    if len(encoded) > max_chars:
        return False, f"Payload too large ({len(encoded)} chars)"

    mode = str(payload.get("mode", "")).strip()
    if mode not in {"duckdb_sql", "sqlite_sql", "python_transform"}:
        return False, "Unsupported mode; expected duckdb_sql, sqlite_sql, or python_transform"

    if mode in {"duckdb_sql", "sqlite_sql"}:
        sql = payload.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return False, "SQL mode requires non-empty 'sql'"
        if MUTATING_SQL_RE.search(sql):
            return False, "Mutating SQL is blocked in sandbox"
        db_path = payload.get("db_path")
        if not isinstance(db_path, str) or not db_path.strip():
            return False, "SQL mode requires non-empty 'db_path'"
        if not _is_path_allowed(db_path):
            return False, f"db_path is outside allowed roots: {db_path}"
        if mode == "sqlite_sql" and not os.path.exists(db_path):
            return False, f"SQLite db_path does not exist: {db_path}"

    if mode == "python_transform":
        code = payload.get("code")
        if not isinstance(code, str) or not code.strip():
            return False, "python_transform requires non-empty 'code'"

    return True, "ok"


def _execute_sqlite_sql(sql: str, db_path: str, row_limit: int) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        fetched = cursor.fetchmany(row_limit)
        rows = [{key: _json_safe(row[key]) for key in row.keys()} for row in fetched]
        columns = list(rows[0].keys()) if rows else [desc[0] for desc in (cursor.description or [])]
        return {"rows": rows, "columns": columns, "row_count": len(rows)}
    finally:
        conn.close()


def _execute_duckdb_sql(sql: str, db_path: str, row_limit: int) -> dict[str, Any]:
    try:
        import duckdb  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("duckdb package is not installed in sandbox runtime") from exc

    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = duckdb.connect(database=db_path)
    try:
        cursor = conn.execute(sql)
        description = cursor.description or []
        columns = [str(item[0]) for item in description if item]
        rows: list[dict[str, Any]] = []
        if columns:
            for raw_row in cursor.fetchmany(row_limit):
                row_dict: dict[str, Any] = {}
                for idx, col in enumerate(columns):
                    value = raw_row[idx] if idx < len(raw_row) else None
                    row_dict[col] = _json_safe(value)
                rows.append(row_dict)
        return {"rows": rows, "columns": columns, "row_count": len(rows)}
    finally:
        conn.close()


def _validate_python_ast(tree: ast.AST) -> None:
    banned = (
        ast.Import,
        ast.ImportFrom,
        ast.With,
        ast.AsyncWith,
        ast.Global,
        ast.Nonlocal,
        ast.Try,
        ast.Raise,
        ast.Delete,
    )
    for node in ast.walk(tree):
        if isinstance(node, banned):
            raise ValueError(f"Disallowed Python syntax in sandbox: {type(node).__name__}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "__import__", "open", "compile", "input"}:
                raise ValueError(f"Blocked function in sandbox code: {node.func.id}")


def _run_python_transform_worker(code: str, input_data: Any, queue: mp.Queue) -> None:
    try:
        tree = ast.parse(code, mode="exec")
        _validate_python_ast(tree)
        compiled = compile(tree, "<sandbox>", "exec")
        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }
        globals_scope = {"__builtins__": safe_builtins}
        locals_scope: dict[str, Any] = {}
        exec(compiled, globals_scope, locals_scope)
        transform = locals_scope.get("transform") or globals_scope.get("transform")
        if not callable(transform):
            raise ValueError("Sandbox code must define: def transform(input_data): ...")
        output = transform(input_data)
        queue.put({"ok": True, "result": _json_safe(output)})
    except Exception as exc:  # noqa: BLE001
        queue.put({"ok": False, "error": str(exc)})


def _execute_python_transform(code: str, input_data: Any) -> Any:
    timeout_seconds = max(1, int(os.getenv("SANDBOX_PY_TIMEOUT_SECONDS", "3")))
    queue: mp.Queue = mp.Queue(maxsize=1)
    proc = mp.Process(target=_run_python_transform_worker, args=(code, input_data, queue))
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        raise TimeoutError(f"Sandbox python execution exceeded {timeout_seconds}s timeout")
    if queue.empty():
        raise RuntimeError("Sandbox execution returned no result")
    payload = queue.get()
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(str(payload.get("error", "sandbox python execution failed")))
    return payload.get("result")


def execute_payload(payload: dict[str, Any]) -> dict[str, Any]:
    trace: list[str] = []
    ok, reason = _validate_payload(payload)
    if not ok:
        return {
            "result": None,
            "trace": [f"validation_failed: {reason}"],
            "validation_status": "failed",
            "error_if_any": reason,
        }

    mode = str(payload.get("mode", ""))
    row_limit = max(1, min(int(payload.get("row_limit", 200)), 5000))
    trace.append(f"validated mode={mode}")

    try:
        if mode == "sqlite_sql":
            result = _execute_sqlite_sql(
                sql=str(payload.get("sql", "")),
                db_path=str(payload.get("db_path", "")),
                row_limit=row_limit,
            )
            trace.append("executed sqlite query")
        elif mode == "duckdb_sql":
            result = _execute_duckdb_sql(
                sql=str(payload.get("sql", "")),
                db_path=str(payload.get("db_path", "")),
                row_limit=row_limit,
            )
            trace.append("executed duckdb query")
        else:
            result = _execute_python_transform(
                code=str(payload.get("code", "")),
                input_data=payload.get("input_data"),
            )
            trace.append("executed python transform")

        return {
            "result": result,
            "trace": trace,
            "validation_status": "passed",
            "error_if_any": None,
        }
    except Exception as exc:  # noqa: BLE001
        trace.append(f"execution_failed: {exc}")
        return {
            "result": None,
            "trace": trace,
            "validation_status": "passed",
            "error_if_any": str(exc),
        }


class SandboxHandler(BaseHTTPRequestHandler):
    server_version = "OracleForgeSandbox/0.1"

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/execute":
            self._json_response(404, {"error": "not_found"})
            return

        try:
            raw_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raw_len = 0
        raw = self.rfile.read(raw_len) if raw_len > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._json_response(
                400,
                {
                    "result": None,
                    "trace": ["validation_failed: invalid json"],
                    "validation_status": "failed",
                    "error_if_any": "invalid json payload",
                },
            )
            return

        if not isinstance(payload, dict):
            self._json_response(
                400,
                {
                    "result": None,
                    "trace": ["validation_failed: payload must be object"],
                    "validation_status": "failed",
                    "error_if_any": "payload must be a json object",
                },
            )
            return

        response = execute_payload(payload)
        status = 200 if response.get("validation_status") == "passed" else 422
        self._json_response(status, response)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        if os.getenv("SANDBOX_QUIET", "1").strip().lower() in {"1", "true", "yes", "on"}:
            return
        super().log_message(format, *args)


def main() -> None:
    port = int(os.getenv("SANDBOX_PORT", "8080"))
    host = os.getenv("SANDBOX_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), SandboxHandler)
    print(f"[sandbox] listening on http://{host}:{port}")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
