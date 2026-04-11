"""Code Sandbox execution layer — U6.

Runs agent-supplied Python snippets in a child subprocess with:
  - 5-second hard timeout (configurable)
  - Stdlib whitelist: json, re, math, datetime, collections
  - Arbitrary named input variables injected via JSON
  - Captures result + stdout + error

Design decisions (from functional design Q&A):
  - Q1=A: subprocess with timeout
  - Q2=B: stdlib whitelist (json, re, math, datetime, collections)
  - Q3=B: 5 second timeout
  - Q4=C: code + named variables dict
  - Q5=A: result + stdout + error output
  - Q8=A: metadata-only logging (session_id, elapsed_ms, success, code_len)

Security:
  - SEC-U6-01: Never log code content or variable values
  - SEC-U6-02: Temp file always deleted in finally block
  - SEC-U6-03: Code length capped at 4096 chars before spawning subprocess
"""
from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any

from agent.models import SandboxResult

_logger = logging.getLogger("agent.sandbox")

_MAX_CODE_LEN = 4096
_DEFAULT_TIMEOUT = 5.0
_ALLOWED_IMPORTS = frozenset({"json", "re", "math", "datetime", "collections"})


def _check_imports(code: str) -> str | None:
    """Return an error string if code imports a non-whitelisted module, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in _ALLOWED_IMPORTS:
                    return f"ImportError: '{top}' is not in the allowed import list"
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top not in _ALLOWED_IMPORTS:
                return f"ImportError: '{top}' is not in the allowed import list"
    return None

# ---------------------------------------------------------------------------
# Runner script template — injected into the child process
# ---------------------------------------------------------------------------

_RUNNER_TEMPLATE = textwrap.dedent("""\
    import sys, json, io

    # Whitelisted imports
    import json as _json_mod
    import re
    import math
    import datetime
    import collections

    # Inject caller-supplied variables
    _vars = json.loads({vars_json!r})
    for _k, _v in _vars.items():
        globals()[_k] = _v

    _stdout_buf = io.StringIO()
    _error = None

    try:
        sys.stdout = _stdout_buf
    {indented_code}
        sys.stdout = sys.__stdout__
    except Exception as _exc:
        sys.stdout = sys.__stdout__
        _error = type(_exc).__name__ + ": " + str(_exc)

    # Capture result from user's global scope
    _result = globals().get("result", None)

    print(json.dumps({{
        "result": _result,
        "stdout": _stdout_buf.getvalue(),
        "error": _error,
    }}))
""")


class CodeSandbox:
    """Execute Python snippets in an isolated subprocess.

    Usage::

        sandbox = CodeSandbox()
        result = await sandbox.execute(
            code='result = [x for x in data if x["score"] > 0.5]',
            variables={"data": [{"score": 0.3}, {"score": 0.8}]},
            session_id="abc-123",
        )
    """

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def execute(
        self,
        code: str,
        variables: dict[str, Any],
        session_id: str = "",
    ) -> SandboxResult:
        """Execute *code* in a subprocess with *variables* pre-bound.

        This method is synchronous — call it from an executor if you need async.
        The orchestrator calls it in the event loop directly (subprocess I/O is
        brief enough that blocking is acceptable for the 5s window).

        Returns SandboxResult — never raises.
        """
        t0 = time.monotonic()

        # Validate inputs before spawning
        if len(code) > _MAX_CODE_LEN:
            return SandboxResult(
                error=f"ValidationError: code exceeds {_MAX_CODE_LEN} chars ({len(code)} given)"
            )
        import_err = _check_imports(code)
        if import_err:
            return SandboxResult(error=import_err)

        try:
            vars_json = json.dumps(variables)
        except (TypeError, ValueError) as exc:
            return SandboxResult(error=f"ValidationError: variables not JSON-serialisable — {exc}")

        tmp_path: str | None = None
        try:
            # Build runner script
            indented = textwrap.indent(code, "    ")
            script = _RUNNER_TEMPLATE.format(
                vars_json=vars_json,
                indented_code=indented,
            )

            # Write to temp file
            fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="oforge_sb_")
            with os.fdopen(fd, "w") as fh:
                fh.write(script)

            # Run in child process
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            raw = proc.stdout.strip()
            if not raw:
                stderr_hint = proc.stderr.strip()[:200] if proc.stderr else ""
                return SandboxResult(
                    error=f"RuntimeError: no output from subprocess. stderr={stderr_hint!r}"
                )

            payload = json.loads(raw)
            result = SandboxResult(
                result=payload.get("result"),
                stdout=payload.get("stdout", ""),
                error=payload.get("error"),
            )

        except subprocess.TimeoutExpired:
            result = SandboxResult(error="TimeoutExpired")
        except json.JSONDecodeError as exc:
            result = SandboxResult(error=f"OutputParseError: {exc}")
        except Exception as exc:  # noqa: BLE001
            result = SandboxResult(error=f"{type(exc).__name__}: {exc}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        elapsed_ms = (time.monotonic() - t0) * 1000
        # SEC-U6-01: log metadata only — never code content or variable values
        _logger.debug(
            "sandbox_execution",
            extra={
                "session_id": session_id,
                "elapsed_ms": round(elapsed_ms, 1),
                "success": result.is_success,
                "code_len": len(code),
            },
        )
        return result
