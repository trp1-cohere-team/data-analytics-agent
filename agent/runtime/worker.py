from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

from agent.data_agent.execution_planner import correct_failed_step, normalize_db_type
from agent.data_agent.failure_diagnostics import diagnose_failure
from agent.data_agent.mcp_toolbox_client import MCPInvocationResult, MCPToolboxClient
from agent.data_agent.openrouter_client import OpenRouterClient
from agent.data_agent.sandbox_client import SandboxClient

from .tooling import ToolPolicy, ToolRegistry

TraceEmitter = Callable[..., None]
CorrectionRecorder = Callable[..., None]


class QueryWorker:
    """Executes individual plan steps and emits execution/correction traces."""

    def __init__(
        self,
        *,
        mcp_client: MCPToolboxClient,
        tool_policy: ToolPolicy,
        client: OpenRouterClient,
        sandbox_client: SandboxClient | None = None,
        use_sandbox: bool = False,
        self_correction_retries: int = 1,
        duckdb_path: str = "./data/duckdb/main.duckdb",
        local_query_row_limit: int = 200,
    ) -> None:
        self.mcp_client = mcp_client
        self.tool_policy = tool_policy
        self.client = client
        self.sandbox_client = sandbox_client
        self.use_sandbox = use_sandbox
        self.self_correction_retries = max(0, self_correction_retries)
        self.duckdb_path = duckdb_path
        self.local_query_row_limit = max(1, int(local_query_row_limit))
        self._postgres_sqlite_cache: dict[str, str] = {}

    def execute_step(
        self,
        *,
        question: str,
        step: dict[str, Any],
        registry: ToolRegistry,
        emit_trace: TraceEmitter,
        record_correction: CorrectionRecorder,
    ) -> dict[str, Any]:
        tool_name = self._resolve_step_tool_name(step, registry)
        tool_input = self._normalize_tool_input(tool_name, step.get("input", {}))
        db_name = str(step.get("database", "unknown_db"))
        use_local_duckdb = self._should_use_local_duckdb(step, registry, tool_name)
        use_local_sqlite = self._should_use_local_sqlite(step)
        use_local_postgres_dump = self._should_use_local_postgres_dump(step)

        emit_trace(
            stage="worker_step_started",
            detail=(
                f"Worker executing step for {db_name} using {tool_name or 'none'}; "
                f"input={self._summarize_input(tool_input)}"
            ),
            tool=tool_name or "none",
            payload={"database": db_name, "input": tool_input},
        )

        allowed, reason = self._check_policy_for_step(
            step=step,
            tool_name=tool_name,
            tool_input=tool_input,
            registry=registry,
            use_local_duckdb=use_local_duckdb,
            use_local_sqlite=use_local_sqlite,
            use_local_postgres_dump=use_local_postgres_dump,
        )
        if not allowed:
            return self._policy_block_response(
                question=question,
                step=step,
                tool_name=tool_name,
                db_name=db_name,
                reason=reason,
                emit_trace=emit_trace,
                record_correction=record_correction,
            )

        result = self._invoke_tool(
            step=step,
            registry=registry,
            tool_name=tool_name,
            tool_input=tool_input,
            use_local_duckdb=use_local_duckdb,
            use_local_sqlite=use_local_sqlite,
            use_local_postgres_dump=use_local_postgres_dump,
        )
        if result.success:
            response_error = self._extract_response_error(result.response)
            if response_error:
                result = MCPInvocationResult(
                    success=False,
                    endpoint=result.endpoint,
                    request_body=result.request_body,
                    response=result.response,
                    error=response_error,
                )
            else:
                emit_trace(
                    stage="tool_execution",
                    detail=f"Executed {tool_name} via {result.endpoint}",
                    tool=tool_name,
                    payload={"database": db_name, "request_body": result.request_body},
                )
                return {
                    "database": db_name,
                    "tool": tool_name,
                    "success": True,
                    "endpoint": result.endpoint,
                    "input": result.request_body,
                    "response": result.response,
                }

        diagnosis = diagnose_failure(
            question=question,
            step=step,
            error_message=result.error or "tool invocation failed",
        )
        emit_trace(
            stage="failure_diagnosed",
            detail=f"Diagnosed failure as {diagnosis.category}: {diagnosis.rationale}",
            tool=tool_name,
            success=False,
            payload={
                "category": diagnosis.category,
                "rationale": diagnosis.rationale,
            },
        )

        corrected = None
        if self.self_correction_retries > 0:
            corrected = self._retry_with_correction(
                question=question,
                step=step,
                registry=registry,
                error_message=result.error or "tool invocation failed",
                diagnosis=diagnosis.category,
                emit_trace=emit_trace,
            )
        if corrected:
            record_correction(
                query=question,
                step=step,
                what_failed=result.error or "tool invocation failed",
                category=diagnosis.category,
                fix_applied=f"Self-correction retry succeeded using {corrected.get('tool')}",
                post_fix_outcome="success",
            )
            return corrected

        emit_trace(
            stage="tool_execution_error",
            detail=(
                f"Failed executing {tool_name}; "
                f"error={result.error or 'unknown'}"
            ),
            tool=tool_name,
            success=False,
        )
        record_correction(
            query=question,
            step=step,
            what_failed=result.error or "tool invocation failed",
            category=diagnosis.category,
            fix_applied="Self-correction attempted but failed",
            post_fix_outcome="failed",
        )
        return {
            "database": db_name,
            "tool": tool_name,
            "success": False,
            "error": result.error or "tool invocation failed",
        }

    def _retry_with_correction(
        self,
        *,
        question: str,
        step: dict[str, Any],
        registry: ToolRegistry,
        error_message: str,
        diagnosis: str,
        emit_trace: TraceEmitter,
    ) -> dict[str, Any] | None:
        current_error = error_message
        available_tools = list(registry.names)
        if "duckdb_query" not in available_tools:
            available_tools.append("duckdb_query")

        rule_corrected = self._rule_based_correction(step=step, error_message=current_error)
        if rule_corrected:
            rule_tool = self._resolve_step_tool_name(rule_corrected, registry)
            rule_input = self._normalize_tool_input(rule_tool, rule_corrected.get("input", {}))
            use_local_duckdb = self._should_use_local_duckdb(
                rule_corrected, registry, rule_tool
            )
            use_local_sqlite = self._should_use_local_sqlite(rule_corrected)
            use_local_postgres_dump = self._should_use_local_postgres_dump(rule_corrected)
            allowed, reason = self._check_policy_for_step(
                step=rule_corrected,
                tool_name=rule_tool,
                tool_input=rule_input,
                registry=registry,
                use_local_duckdb=use_local_duckdb,
                use_local_sqlite=use_local_sqlite,
                use_local_postgres_dump=use_local_postgres_dump,
            )
            if allowed:
                rule_result = self._invoke_tool(
                    step=rule_corrected,
                    registry=registry,
                    tool_name=rule_tool,
                    tool_input=rule_input,
                    use_local_duckdb=use_local_duckdb,
                    use_local_sqlite=use_local_sqlite,
                    use_local_postgres_dump=use_local_postgres_dump,
                )
                if rule_result.success:
                    response_error = self._extract_response_error(rule_result.response)
                    if not response_error:
                        emit_trace(
                            stage="self_correction_success",
                            detail=(
                                "Recovered failed tool call using rule-based SQL correction "
                                "for relation qualifier mismatch."
                            ),
                            tool=rule_tool,
                        )
                        return {
                            "database": rule_corrected.get(
                                "database", step.get("database", "unknown_db")
                            ),
                            "tool": rule_tool,
                            "success": True,
                            "endpoint": rule_result.endpoint,
                            "input": rule_result.request_body,
                            "response": rule_result.response,
                            "corrected": True,
                        }
                    current_error = response_error
                else:
                    current_error = rule_result.error or "rule-based correction failed"
            else:
                current_error = reason

        for attempt in range(1, self.self_correction_retries + 1):
            corrected = correct_failed_step(
                client=self.client,
                question=question,
                step=step,
                error_message=current_error,
                available_tools=available_tools,
                diagnosis=diagnosis,
            )
            if not corrected:
                return None

            corrected_tool = self._resolve_step_tool_name(corrected, registry)
            corrected_input = self._normalize_tool_input(
                corrected_tool, corrected.get("input", {})
            )
            use_local_duckdb = self._should_use_local_duckdb(
                corrected, registry, corrected_tool
            )
            use_local_sqlite = self._should_use_local_sqlite(corrected)
            use_local_postgres_dump = self._should_use_local_postgres_dump(corrected)
            allowed, reason = self._check_policy_for_step(
                step=corrected,
                tool_name=corrected_tool,
                tool_input=corrected_input,
                registry=registry,
                use_local_duckdb=use_local_duckdb,
                use_local_sqlite=use_local_sqlite,
                use_local_postgres_dump=use_local_postgres_dump,
            )
            if not allowed:
                current_error = reason
                continue

            corrected_result = self._invoke_tool(
                step=corrected,
                registry=registry,
                tool_name=corrected_tool,
                tool_input=corrected_input,
                use_local_duckdb=use_local_duckdb,
                use_local_sqlite=use_local_sqlite,
                use_local_postgres_dump=use_local_postgres_dump,
            )
            if corrected_result.success:
                response_error = self._extract_response_error(corrected_result.response)
                if response_error:
                    current_error = response_error
                    continue
                emit_trace(
                    stage="self_correction_success",
                    detail=f"Recovered failed tool call on attempt {attempt}",
                    tool=corrected_tool,
                )
                return {
                    "database": corrected.get("database", step.get("database", "unknown_db")),
                    "tool": corrected_tool,
                    "success": True,
                    "endpoint": corrected_result.endpoint,
                    "input": corrected_result.request_body,
                    "response": corrected_result.response,
                    "corrected": True,
                }

            current_error = corrected_result.error or "corrected invocation failed"

        emit_trace(
            stage="self_correction_failed",
            detail=f"Correction retries exhausted. Last error: {current_error}",
            tool="self_correction",
            success=False,
        )
        return None

    def can_execute_without_mcp(
        self,
        *,
        step: dict[str, Any],
        registry: ToolRegistry,
    ) -> bool:
        tool_name = self._resolve_step_tool_name(step, registry)
        return (
            self._should_use_local_duckdb(step, registry, tool_name)
            or self._should_use_local_sqlite(step)
            or self._should_use_local_postgres_dump(step)
        )

    def _resolve_step_tool_name(
        self,
        step: dict[str, Any],
        registry: ToolRegistry,
    ) -> str:
        resolved = registry.resolve_for_step(step) or str(step.get("tool", ""))
        if resolved:
            return resolved

        db_type = normalize_db_type(str(step.get("db_type", "")))
        if db_type == "duckdb":
            return "duckdb_query"
        return ""

    def _check_policy_for_step(
        self,
        *,
        step: dict[str, Any],
        tool_name: str,
        tool_input: dict[str, Any],
        registry: ToolRegistry,
        use_local_duckdb: bool,
        use_local_sqlite: bool,
        use_local_postgres_dump: bool,
    ) -> tuple[bool, str]:
        if use_local_duckdb or use_local_sqlite or use_local_postgres_dump:
            return self._check_local_duckdb_policy(tool_input)
        return self.tool_policy.check(tool_name, tool_input, registry)

    def _check_local_duckdb_policy(
        self, tool_input: dict[str, Any]
    ) -> tuple[bool, str]:
        if not isinstance(tool_input, dict):
            return False, "Tool input must be a JSON object"

        payload_len = len(json.dumps(tool_input, ensure_ascii=False))
        if payload_len > self.tool_policy.max_payload_chars:
            return False, f"Tool input too large ({payload_len} chars)"

        sql = tool_input.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return False, "DuckDB local execution requires non-empty input.sql"

        if self.tool_policy.is_mutating_sql(sql):
            return False, "Write/mutation SQL is blocked by policy"

        return True, "allowed"

    def _should_use_local_duckdb(
        self,
        step: dict[str, Any],
        registry: ToolRegistry,
        tool_name: str,
    ) -> bool:
        db_type = normalize_db_type(str(step.get("db_type", "")))
        if db_type != "duckdb":
            return False

        discovered_duck_tool = registry.suggest_for_db_type("duckdb")
        if discovered_duck_tool:
            return False

        return (not tool_name) or ("duck" in tool_name.lower())

    @staticmethod
    def _should_use_local_sqlite(step: dict[str, Any]) -> bool:
        db_type = normalize_db_type(str(step.get("db_type", "")))
        if db_type != "sqlite":
            return False
        db_path = step.get("db_path")
        return isinstance(db_path, str) and bool(db_path.strip())

    @staticmethod
    def _should_use_local_postgres_dump(step: dict[str, Any]) -> bool:
        db_type = normalize_db_type(str(step.get("db_type", "")))
        if db_type != "postgresql":
            return False
        sql_file = step.get("sql_file")
        return isinstance(sql_file, str) and bool(sql_file.strip())

    def _invoke_tool(
        self,
        *,
        step: dict[str, Any],
        registry: ToolRegistry,
        tool_name: str,
        tool_input: dict[str, Any],
        use_local_duckdb: bool,
        use_local_sqlite: bool,
        use_local_postgres_dump: bool,
    ):
        if use_local_duckdb:
            if self.use_sandbox and self.sandbox_client is not None:
                return self._invoke_sql_via_sandbox(
                    mode="duckdb_sql",
                    sql=str(tool_input.get("sql", "")),
                    db_path=str(tool_input.get("db_path", self.duckdb_path)),
                    row_limit=self._resolve_local_row_limit(step),
                )
            return self._invoke_duckdb_local(tool_input=tool_input)
        if use_local_sqlite:
            if self.use_sandbox and self.sandbox_client is not None:
                db_path = str(step.get("db_path", "")).strip()
                return self._invoke_sql_via_sandbox(
                    mode="sqlite_sql",
                    sql=str(tool_input.get("sql", "")),
                    db_path=db_path,
                    row_limit=self._resolve_local_row_limit(step),
                )
            return self._invoke_sqlite_local(step=step, tool_input=tool_input)
        if use_local_postgres_dump:
            return self._invoke_postgres_dump_local(step=step, tool_input=tool_input)
        return self.mcp_client.invoke_tool(tool_name=tool_name, tool_input=tool_input)

    def _invoke_sql_via_sandbox(
        self,
        *,
        mode: str,
        sql: str,
        db_path: str,
        row_limit: int,
    ) -> MCPInvocationResult:
        if self.sandbox_client is None:
            return MCPInvocationResult(
                success=False,
                endpoint="sandbox://unconfigured",
                request_body={"mode": mode, "sql": sql, "db_path": db_path},
                response=None,
                error="Sandbox client is not configured",
            )

        payload: dict[str, Any] = {
            "mode": mode,
            "sql": sql,
            "row_limit": row_limit,
        }
        if db_path:
            payload["db_path"] = db_path

        result = self.sandbox_client.execute(payload)
        if not result.success:
            return MCPInvocationResult(
                success=False,
                endpoint=f"sandbox://{result.endpoint.lstrip('/')}",
                request_body=result.request_body,
                response=result.response,
                error=result.error or "sandbox execution failed",
            )

        response_payload: Any = result.response or {}
        if isinstance(response_payload, dict) and "result" in response_payload:
            response_payload = response_payload.get("result")
        return MCPInvocationResult(
            success=True,
            endpoint=f"sandbox://{result.endpoint.lstrip('/')}",
            request_body=result.request_body,
            response=response_payload,
        )

    def _invoke_sqlite_local(
        self,
        *,
        step: dict[str, Any],
        tool_input: dict[str, Any],
    ) -> MCPInvocationResult:
        sql = str(tool_input.get("sql", "")).strip()
        if not sql:
            return MCPInvocationResult(
                success=False,
                endpoint="local://sqlite",
                request_body={"sql": ""},
                response=None,
                error="SQLite local execution requires non-empty input.sql",
            )

        db_path = str(step.get("db_path", "")).strip()
        if not db_path:
            return MCPInvocationResult(
                success=False,
                endpoint="local://sqlite",
                request_body={"sql": sql},
                response=None,
                error="SQLite local execution requires step.db_path",
            )

        if not os.path.exists(db_path):
            return MCPInvocationResult(
                success=False,
                endpoint="local://sqlite",
                request_body={"sql": sql, "db_path": db_path},
                response=None,
                error=f"SQLite db_path does not exist: {db_path}",
            )

        translated_sql = self._translate_sql_for_sqlite(sql)
        row_limit = self._resolve_local_row_limit(step)
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(translated_sql)
                rows: list[dict[str, Any]] = []
                fetched = cur.fetchmany(row_limit)
                for row in fetched:
                    rows.append({key: self._to_json_safe(row[key]) for key in row.keys()})
                response = {
                    "rows": rows,
                    "columns": list(rows[0].keys()) if rows else [desc[0] for desc in (cur.description or [])],
                    "row_count": len(rows),
                }
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return MCPInvocationResult(
                success=False,
                endpoint="local://sqlite",
                request_body={"sql": translated_sql, "db_path": db_path},
                response=None,
                error=f"sqlite error: {exc}",
            )

        return MCPInvocationResult(
            success=True,
            endpoint="local://sqlite",
            request_body={"sql": translated_sql, "db_path": db_path},
            response=response,
        )

    def _invoke_postgres_dump_local(
        self,
        *,
        step: dict[str, Any],
        tool_input: dict[str, Any],
    ) -> MCPInvocationResult:
        sql = str(tool_input.get("sql", "")).strip()
        if not sql:
            return MCPInvocationResult(
                success=False,
                endpoint="local://postgres-dump",
                request_body={"sql": ""},
                response=None,
                error="Postgres dump local execution requires non-empty input.sql",
            )

        sql_file = str(step.get("sql_file", "")).strip()
        if not sql_file:
            return MCPInvocationResult(
                success=False,
                endpoint="local://postgres-dump",
                request_body={"sql": sql},
                response=None,
                error="Postgres dump local execution requires step.sql_file",
            )
        if not os.path.exists(sql_file):
            return MCPInvocationResult(
                success=False,
                endpoint="local://postgres-dump",
                request_body={"sql": sql, "sql_file": sql_file},
                response=None,
                error=f"sql_file does not exist: {sql_file}",
            )

        try:
            sqlite_path = self._materialize_postgres_dump_to_sqlite(sql_file)
        except Exception as exc:  # noqa: BLE001
            return MCPInvocationResult(
                success=False,
                endpoint="local://postgres-dump",
                request_body={"sql": sql, "sql_file": sql_file},
                response=None,
                error=f"failed to materialize sql_file: {exc}",
            )

        translated_sql = self._translate_sql_for_sqlite(sql)
        row_limit = self._resolve_local_row_limit(step)
        try:
            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(translated_sql)
                rows: list[dict[str, Any]] = []
                fetched = cur.fetchmany(row_limit)
                for row in fetched:
                    rows.append({key: self._to_json_safe(row[key]) for key in row.keys()})
                response = {
                    "rows": rows,
                    "columns": list(rows[0].keys()) if rows else [desc[0] for desc in (cur.description or [])],
                    "row_count": len(rows),
                }
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return MCPInvocationResult(
                success=False,
                endpoint="local://postgres-dump",
                request_body={"sql": translated_sql, "sql_file": sql_file, "sqlite_path": sqlite_path},
                response=None,
                error=f"sqlite emulation error: {exc}",
            )

        return MCPInvocationResult(
            success=True,
            endpoint="local://postgres-dump",
            request_body={"sql": translated_sql, "sql_file": sql_file, "sqlite_path": sqlite_path},
            response=response,
        )

    def _materialize_postgres_dump_to_sqlite(self, sql_file: str) -> str:
        resolved = str(Path(sql_file).resolve())
        stat = os.stat(resolved)
        cache_key = f"{resolved}:{int(stat.st_mtime)}:{stat.st_size}"
        if cache_key in self._postgres_sqlite_cache:
            cached = self._postgres_sqlite_cache[cache_key]
            if os.path.exists(cached):
                return cached

        cache_root = Path(self.duckdb_path).resolve().parent / "_postgres_sqlite_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()  # noqa: S324
        sqlite_path = str((cache_root / f"{digest}.sqlite").resolve())

        if os.path.exists(sqlite_path):
            self._postgres_sqlite_cache[cache_key] = sqlite_path
            return sqlite_path

        conn = sqlite3.connect(sqlite_path)
        try:
            self._load_postgres_dump_into_sqlite(resolved, conn)
            conn.commit()
        finally:
            conn.close()

        self._postgres_sqlite_cache[cache_key] = sqlite_path
        return sqlite_path

    def _load_postgres_dump_into_sqlite(self, sql_file: str, conn: sqlite3.Connection) -> None:
        with open(sql_file, encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()

        idx = 0
        while idx < len(lines):
            raw_line = lines[idx]
            line = raw_line.strip()
            if not line:
                idx += 1
                continue

            upper = line.upper()
            if upper.startswith("CREATE TABLE"):
                create_lines = [raw_line]
                idx += 1
                while idx < len(lines):
                    create_lines.append(lines[idx])
                    if lines[idx].strip().endswith(");"):
                        idx += 1
                        break
                    idx += 1
                self._execute_sqlite_create(conn, create_lines)
                continue

            if upper.startswith("INSERT INTO"):
                converted = self._convert_insert_statement(raw_line)
                if converted:
                    try:
                        conn.execute(converted)
                    except sqlite3.Error:
                        pass
                idx += 1
                continue

            if upper.startswith("COPY ") and " FROM STDIN" in upper:
                idx = self._consume_copy_block(conn, lines, idx)
                continue

            idx += 1

    @staticmethod
    def _convert_insert_statement(statement: str) -> str:
        cleaned = statement.replace("public.", "")
        return cleaned

    def _execute_sqlite_create(self, conn: sqlite3.Connection, create_lines: list[str]) -> None:
        header = create_lines[0].strip()
        match = re.search(r"CREATE\s+TABLE\s+([^\s(]+)\s*\(", header, flags=re.IGNORECASE)
        if not match:
            return
        raw_table = match.group(1).replace("public.", "").strip().strip('"')
        columns: list[tuple[str, str]] = []
        for raw in create_lines[1:]:
            line = raw.strip().rstrip(",")
            if not line or line == ");":
                continue
            if line.upper().startswith("CONSTRAINT"):
                continue
            col_match = re.match(r'("?[^"\s]+"?)\s+(.+)$', line)
            if not col_match:
                continue
            name = col_match.group(1).strip().strip('"')
            raw_type = col_match.group(2).strip().lower()
            sql_type = "TEXT"
            if "int" in raw_type:
                sql_type = "INTEGER"
            elif "double" in raw_type or "numeric" in raw_type or "real" in raw_type or "float" in raw_type:
                sql_type = "REAL"
            elif "bool" in raw_type:
                sql_type = "INTEGER"
            columns.append((name, sql_type))
        if not columns:
            return
        cols_ddl = ", ".join(f'"{name}" {dtype}' for name, dtype in columns)
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{raw_table}" ({cols_ddl});')

    def _consume_copy_block(
        self,
        conn: sqlite3.Connection,
        lines: list[str],
        start_idx: int,
    ) -> int:
        header = lines[start_idx].strip()
        match = re.match(
            r'^COPY\s+([^\s(]+)\s*\((.+)\)\s+FROM\s+stdin;$',
            header,
            flags=re.IGNORECASE,
        )
        if not match:
            return start_idx + 1

        table = match.group(1).replace("public.", "").strip().strip('"')
        cols = [col.strip().strip('"') for col in match.group(2).split(",")]
        placeholders = ", ".join(["?"] * len(cols))
        columns_sql = ", ".join(f'"{col}"' for col in cols)
        insert_sql = f'INSERT INTO "{table}" ({columns_sql}) VALUES ({placeholders})'

        idx = start_idx + 1
        batch: list[tuple[Any, ...]] = []
        while idx < len(lines):
            row_line = lines[idx].rstrip("\n")
            if row_line == r"\.":
                if batch:
                    conn.executemany(insert_sql, batch)
                    batch.clear()
                return idx + 1

            fields = row_line.split("\t")
            decoded = tuple(self._decode_pg_copy_field(field) for field in fields)
            batch.append(decoded)
            if len(batch) >= 1000:
                conn.executemany(insert_sql, batch)
                batch.clear()
            idx += 1

        if batch:
            conn.executemany(insert_sql, batch)
        return idx

    @staticmethod
    def _decode_pg_copy_field(field: str) -> Any:
        if field == r"\N":
            return None
        out: list[str] = []
        i = 0
        while i < len(field):
            ch = field[i]
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            if i + 1 >= len(field):
                out.append("\\")
                i += 1
                continue
            nxt = field[i + 1]
            mapping = {
                "n": "\n",
                "t": "\t",
                "r": "\r",
                "b": "\b",
                "f": "\f",
                "v": "\v",
                "\\": "\\",
            }
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if nxt.isdigit():
                octal = nxt
                j = i + 2
                while j < len(field) and len(octal) < 3 and field[j].isdigit():
                    octal += field[j]
                    j += 1
                try:
                    out.append(chr(int(octal, 8)))
                except ValueError:
                    out.append(octal)
                i = j
                continue
            out.append(nxt)
            i += 2
        return "".join(out)

    @staticmethod
    def _translate_sql_for_sqlite(sql: str) -> str:
        translated = sql
        translated = re.sub(r"\bpublic\.", "", translated, flags=re.IGNORECASE)
        translated = re.sub(r"\bILIKE\b", "LIKE", translated, flags=re.IGNORECASE)
        translated = re.sub(r"::\s*[A-Za-z_][A-Za-z0-9_]*", "", translated)
        translated = re.sub(r"\bTRUE\b", "1", translated, flags=re.IGNORECASE)
        translated = re.sub(r"\bFALSE\b", "0", translated, flags=re.IGNORECASE)
        return translated

    def _resolve_local_row_limit(self, step: dict[str, Any]) -> int:
        raw = step.get("row_limit")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.local_query_row_limit
        return max(1, min(value, 5000))

    def _invoke_duckdb_local(self, *, tool_input: dict[str, Any]):
        sql = str(tool_input.get("sql", "")).strip()
        if not sql:
            return MCPInvocationResult(
                success=False,
                endpoint="local://duckdb",
                request_body={"sql": ""},
                response=None,
                error="DuckDB local execution requires non-empty input.sql",
            )

        try:
            import duckdb  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return MCPInvocationResult(
                success=False,
                endpoint="local://duckdb",
                request_body={"sql": sql},
                response=None,
                error=(
                    "Python package 'duckdb' is not installed. "
                    "Run: pip install duckdb"
                ),
            )

        try:
            override_path = tool_input.get("db_path")
            db_path = (
                str(override_path).strip()
                if isinstance(override_path, str) and str(override_path).strip()
                else self.duckdb_path
            )
            if os.path.exists(db_path):
                try:
                    with open(db_path, "rb") as handle:
                        head = handle.read(256).decode("utf-8", errors="ignore")
                    if "git-lfs.github.com/spec/v1" in head:
                        return MCPInvocationResult(
                            success=False,
                            endpoint="local://duckdb",
                            request_body={"sql": sql, "db_path": db_path},
                            response=None,
                            error=(
                                f"DuckDB file '{db_path}' is a Git LFS pointer, not real data. "
                                "Run 'git lfs install && git lfs pull' in external/DataAgentBench."
                            ),
                        )
                except OSError:
                    # Continue and let connection errors surface with original cause.
                    pass
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
                    raw_rows = cursor.fetchmany(self.local_query_row_limit)
                    for row in raw_rows:
                        row_dict: dict[str, Any] = {}
                        for idx, column in enumerate(columns):
                            value = row[idx] if idx < len(row) else None
                            row_dict[column] = self._to_json_safe(value)
                        rows.append(row_dict)

                response: dict[str, Any] = {
                    "rows": rows,
                    "columns": columns,
                    "row_count": len(rows),
                }
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            return MCPInvocationResult(
                success=False,
                endpoint="local://duckdb",
                request_body={"sql": sql, "db_path": db_path},
                response=None,
                error=str(exc),
            )

        return MCPInvocationResult(
            success=True,
            endpoint="local://duckdb",
            request_body={"sql": sql, "db_path": db_path},
            response=response,
        )

    @staticmethod
    def _extract_response_error(response: Any) -> str | None:
        if response is None:
            return None

        def _looks_like_error_text(text: str) -> bool:
            lowered = text.strip().lower()
            if not lowered:
                return False
            error_patterns = [
                "relation",
                "does not exist",
                "no such table",
                "syntax error",
                "parser error",
                "column",
                "unknown column",
                "exception",
                "traceback",
                "permission denied",
                "failed",
                "invalid",
            ]
            if any(pattern in lowered for pattern in error_patterns):
                # avoid false positives such as "0 failed rows" style strings
                return bool(
                    re.search(
                        r"(does not exist|no such table|syntax error|parser error|"
                        r"exception|traceback|permission denied|unknown column|"
                        r"relation\s+['\"`].+['\"`])",
                        lowered,
                    )
                ) or lowered.startswith("error")
            return False

        def _extract_text(value: Any) -> str | None:
            if isinstance(value, str):
                return value.strip() or None
            return None

        def _walk(value: Any) -> str | None:
            if isinstance(value, str):
                return value if _looks_like_error_text(value) else None

            if isinstance(value, dict):
                if value.get("isError") is True:
                    for key in ("content", "result", "data", "output"):
                        if key in value:
                            walked = _walk(value.get(key))
                            if walked:
                                return walked
                    for key in ("error", "message", "text"):
                        text = _extract_text(value.get(key))
                        if text:
                            return text
                    return "Tool returned isError=true"

                for key in ("error", "errors", "exception", "traceback"):
                    nested = value.get(key)
                    if nested:
                        if isinstance(nested, str):
                            return nested
                        walked = _walk(nested)
                        if walked:
                            return walked

                for key in ("message", "text"):
                    text = _extract_text(value.get(key))
                    if text and _looks_like_error_text(text):
                        return text

                for key in ("content", "result", "data", "output"):
                    if key in value:
                        walked = _walk(value.get(key))
                        if walked:
                            return walked
                return None

            if isinstance(value, list):
                for item in value:
                    walked = _walk(item)
                    if walked:
                        return walked
                return None

            return None

        return _walk(response)

    def _rule_based_correction(
        self,
        *,
        step: dict[str, Any],
        error_message: str,
    ) -> dict[str, Any] | None:
        db_type = normalize_db_type(str(step.get("db_type", "")))
        if db_type not in {"postgresql", "sqlite", "duckdb"}:
            return None

        step_input = step.get("input")
        if not isinstance(step_input, dict):
            return None

        query_key = "query" if isinstance(step_input.get("query"), str) else "sql"
        sql = step_input.get(query_key)
        if not isinstance(sql, str) or not sql.strip():
            return None

        repaired_sql = sql
        prefixes: set[str] = set()
        missing_relations: set[str] = set()
        patterns = [
            r"relation\s+[\"'`]?([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)[\"'`]?\s+does\s+not\s+exist",
            r"no\s+such\s+table:\s*([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
        ]
        missing_patterns = [
            r"relation\s+[\"'`]?([a-zA-Z_][a-zA-Z0-9_\.]*)[\"'`]?\s+does\s+not\s+exist",
            r"no\s+such\s+table:\s*([a-zA-Z_][a-zA-Z0-9_\.]*)",
        ]
        lowered_error = error_message.lower()
        for pattern in patterns:
            for match in re.findall(pattern, lowered_error, flags=re.IGNORECASE):
                if isinstance(match, tuple) and match:
                    prefixes.add(str(match[0]))
        for pattern in missing_patterns:
            for match in re.findall(pattern, lowered_error, flags=re.IGNORECASE):
                if isinstance(match, str) and match.strip():
                    missing_relations.add(match.strip())

        # fallback: strip obvious *_db qualifiers in SQL
        if not prefixes:
            for prefix in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*_db)\s*\.", repaired_sql):
                prefixes.add(prefix)

        for prefix in sorted(prefixes, key=len, reverse=True):
            repaired_sql = re.sub(
                rf'\b{re.escape(prefix)}\s*\.',
                "",
                repaired_sql,
                flags=re.IGNORECASE,
            )
            repaired_sql = re.sub(
                rf'"{re.escape(prefix)}"\s*\.',
                "",
                repaired_sql,
                flags=re.IGNORECASE,
            )

        known_objects_raw = step.get("known_objects")
        known_objects: list[str] = []
        if isinstance(known_objects_raw, list):
            for item in known_objects_raw:
                candidate = str(item).strip()
                if not candidate:
                    continue
                if any(candidate.lower().endswith(ext) for ext in (".db", ".duckdb", ".sqlite", ".sql")):
                    continue
                if "(" in candidate or ")" in candidate:
                    continue
                known_objects.append(candidate)

        if known_objects and missing_relations:
            for missing in sorted(missing_relations, key=len, reverse=True):
                replacement = self._choose_known_object(missing, known_objects)
                if not replacement:
                    continue
                # Replace both qualified and bare variants.
                missing_last = missing.split(".")[-1]
                variants = {missing, missing_last}
                for variant in sorted(variants, key=len, reverse=True):
                    repaired_sql = re.sub(
                        rf'\b{re.escape(variant)}\b',
                        replacement,
                        repaired_sql,
                        flags=re.IGNORECASE,
                    )
                    repaired_sql = re.sub(
                        rf'"{re.escape(variant)}"',
                        replacement,
                        repaired_sql,
                        flags=re.IGNORECASE,
                    )

        if repaired_sql == sql:
            return None

        corrected_input = dict(step_input)
        corrected_input[query_key] = repaired_sql
        corrected_input["sql"] = repaired_sql

        corrected_step = dict(step)
        corrected_step["input"] = corrected_input
        corrected_step["reason"] = (
            "Rule-based qualifier fix: removed database-name prefixes from table references."
        )
        return corrected_step

    @staticmethod
    def _choose_known_object(missing: str, known_objects: list[str]) -> str | None:
        missing_norm = missing.strip().strip('"').strip("'").split(".")[-1].lower()
        if not missing_norm:
            return None

        normalized_candidates: list[tuple[str, str]] = []
        for obj in known_objects:
            table = obj.strip().strip('"').strip("'").split(".")[-1]
            if not table:
                continue
            normalized_candidates.append((obj, table))

        # Exact match
        for original, table in normalized_candidates:
            if table.lower() == missing_norm:
                return table

        # Substring or stem-like match
        for original, table in normalized_candidates:
            lower_table = table.lower()
            if missing_norm in lower_table or lower_table in missing_norm:
                return table

        # Closest lexical match
        table_names = [table for _, table in normalized_candidates]
        table_names_lower = [table.lower() for table in table_names]
        close = difflib.get_close_matches(missing_norm, table_names_lower, n=1, cutoff=0.55)
        if not close:
            return None

        target_lower = close[0]
        for table in table_names:
            if table.lower() == target_lower:
                return table
        return None

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            return [QueryWorker._to_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): QueryWorker._to_json_safe(item)
                for key, item in value.items()
            }
        return str(value)

    def _policy_block_response(
        self,
        *,
        question: str,
        step: dict[str, Any],
        tool_name: str,
        db_name: str,
        reason: str,
        emit_trace: TraceEmitter,
        record_correction: CorrectionRecorder,
    ) -> dict[str, Any]:
        diagnosis = diagnose_failure(
            question=question,
            step=step,
            error_message=reason,
        )
        emit_trace(
            stage="tool_policy_block",
            detail=reason,
            tool=tool_name or "none",
            success=False,
        )
        emit_trace(
            stage="failure_diagnosed",
            detail=(
                f"Diagnosed failure as {diagnosis.category}: "
                f"{diagnosis.rationale}"
            ),
            tool=tool_name or "none",
            success=False,
            payload={
                "category": diagnosis.category,
                "rationale": diagnosis.rationale,
            },
        )
        record_correction(
            query=question,
            step=step,
            what_failed=reason,
            category=diagnosis.category,
            fix_applied="Policy denied execution; adjust query/tool input to comply.",
            post_fix_outcome="failed",
        )
        return {
            "database": db_name,
            "tool": tool_name or "none",
            "success": False,
            "error": reason,
            "policy_blocked": True,
        }

    @staticmethod
    def _summarize_input(tool_input: Any) -> str:
        if not isinstance(tool_input, dict):
            return type(tool_input).__name__

        query = tool_input.get("query")
        if isinstance(query, str):
            return query.strip().replace("\n", " ")[:160]
        sql = tool_input.get("sql")
        if isinstance(sql, str):
            return sql.strip().replace("\n", " ")[:160]

        collection = tool_input.get("collection")
        pipeline = tool_input.get("pipeline")
        if isinstance(collection, str):
            if isinstance(pipeline, list):
                return (
                    f"collection={collection}, "
                    f"pipeline_stages={len(pipeline)}"
                )
            return f"collection={collection}"

        keys = ", ".join(sorted(str(key) for key in tool_input.keys()))
        return f"keys=[{keys}]"

    @staticmethod
    def _normalize_tool_input(tool_name: str, tool_input: Any) -> dict[str, Any]:
        if not isinstance(tool_input, dict):
            return {}

        normalized = dict(tool_input)

        # Toolbox execute-sql tools expect `sql`; planner currently emits `query`.
        query = normalized.get("query")
        if isinstance(query, str) and "sql" not in normalized:
            normalized["sql"] = query

        # Toolbox mongodb-aggregate can accept pipeline as a JSON string param.
        pipeline = normalized.get("pipeline")
        if isinstance(pipeline, (list, dict)):
            normalized["pipeline"] = json.dumps(pipeline, ensure_ascii=False)

        return normalized
