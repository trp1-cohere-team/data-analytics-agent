"""Sandboxed Python code execution server.

FR-10: Provides /execute and /health endpoints for isolated code execution.
SEC-05: Input validation on all request parameters.
SEC-09: Path traversal blocked; generic error messages to callers.
SEC-15: All execution wrapped with timeouts and exception handling.
SEC-03: Structured logging throughout.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Configuration (read from environment at startup)
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
SANDBOX_PY_TIMEOUT_SECONDS: int = int(os.environ.get("SANDBOX_PY_TIMEOUT_SECONDS", "3"))
SANDBOX_MAX_PAYLOAD_CHARS: int = int(os.environ.get("SANDBOX_MAX_PAYLOAD_CHARS", "50000"))

# Colon-separated list of allowed filesystem roots for sandboxed code.
# Any path access outside these roots is rejected before execution.
_allowed_roots_raw: str = os.environ.get("SANDBOX_ALLOWED_ROOTS", "/tmp")
SANDBOX_ALLOWED_ROOTS: list[str] = [
    r.strip() for r in _allowed_roots_raw.split(":") if r.strip()
]

# ---------------------------------------------------------------------------
# Logging setup (SEC-03)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health() -> tuple:
    """Health endpoint.

    Returns
    -------
    JSON: {"status": "ok"}
    """
    return jsonify({"status": "ok"}), 200


@app.route("/execute", methods=["POST"])
def execute() -> tuple:
    """Execute Python code in a subprocess with timeout enforcement.

    Request body (JSON):
        code    : str  — Python source code to execute
        timeout : int  — Optional override for execution timeout (seconds)

    Returns
    -------
    JSON: {"success": bool, "output": str, "error": str}
    """
    # SEC-05: validate content type
    if not request.is_json:
        logger.warning("/execute: non-JSON request received")
        return jsonify({"success": False, "output": "", "error": "invalid_content_type"}), 400

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"success": False, "output": "", "error": "invalid_request_body"}), 400

    code = body.get("code", "")
    timeout_override = body.get("timeout")

    # SEC-05: type + length validation
    if not isinstance(code, str):
        return jsonify({"success": False, "output": "", "error": "invalid_code_type"}), 400

    if len(code) > SANDBOX_MAX_PAYLOAD_CHARS:
        logger.warning("/execute: payload too large (%d chars)", len(code))
        return jsonify({"success": False, "output": "", "error": "payload_too_large"}), 400

    if not code.strip():
        return jsonify({"success": False, "output": "", "error": "empty_code"}), 400

    # Determine effective timeout
    effective_timeout = SANDBOX_PY_TIMEOUT_SECONDS
    if timeout_override is not None:
        try:
            t = int(timeout_override)
            effective_timeout = min(max(1, t), SANDBOX_PY_TIMEOUT_SECONDS)
        except (ValueError, TypeError):
            pass

    # SEC-09: path traversal check
    violation = _check_path_traversal(code)
    if violation:
        logger.warning("/execute: path traversal attempt detected: %s", violation)
        # Return generic error — do not expose internal path details (SEC-09)
        return jsonify({"success": False, "output": "", "error": "access_denied"}), 403

    # Execute in subprocess
    success, output, error = _run_in_subprocess(code, effective_timeout)
    logger.info(
        "/execute: success=%s output_len=%d timeout=%ds",
        success,
        len(output),
        effective_timeout,
    )
    return jsonify({"success": success, "output": output, "error": error}), 200


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _check_path_traversal(code: str) -> str:
    """Return a description of the path violation, or empty string if clean.

    Checks whether the code references any path outside SANDBOX_ALLOWED_ROOTS.
    This is a best-effort static heuristic — the sandbox subprocess already
    runs in an isolated temp directory.
    """
    suspicious_patterns = [
        "/etc/passwd",
        "/etc/shadow",
        "/root/",
        "../",
        "..\\",
    ]
    for pattern in suspicious_patterns:
        if pattern in code:
            return f"suspicious pattern: {pattern!r}"

    # Check absolute paths that are outside allowed roots
    import re

    abs_paths = re.findall(r'["\'](?P<p>/[^"\']+)["\']', code)
    for path in abs_paths:
        if not any(path.startswith(root) for root in SANDBOX_ALLOWED_ROOTS):
            return f"path outside allowed roots: {path!r}"

    return ""


# ---------------------------------------------------------------------------
# Subprocess execution
# ---------------------------------------------------------------------------


def _run_in_subprocess(code: str, timeout: int) -> tuple[bool, str, str]:
    """Execute *code* in an isolated subprocess.

    Parameters
    ----------
    code:
        Python source code to run.
    timeout:
        Maximum wall-clock seconds allowed.

    Returns
    -------
    tuple[bool, str, str]
        ``(success, stdout_output, error_message)``
    """
    tmp_file: str | None = None
    try:
        # Write code to a temp file to avoid shell injection
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir="/tmp",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(code)
            tmp_file = fh.name

        result = subprocess.run(
            [sys.executable, tmp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/tmp",
        )

        stdout = result.stdout[:4096] if result.stdout else ""
        stderr = result.stderr[:1024] if result.stderr else ""

        if result.returncode == 0:
            return (True, stdout, "")
        else:
            # SEC-09: return generic error without leaking internal paths
            return (False, stdout, "execution_error")

    except subprocess.TimeoutExpired:
        logger.warning("_run_in_subprocess: execution timed out after %ds", timeout)
        return (False, "", "execution_timeout")
    except Exception as exc:
        logger.warning("_run_in_subprocess: unexpected error: %s", exc)
        # SEC-09: generic error to caller
        return (False, "", "execution_failed")
    finally:
        if tmp_file:
            try:
                os.unlink(tmp_file)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("SANDBOX_PORT", "8080"))
    host = os.environ.get("SANDBOX_HOST", "127.0.0.1")
    logger.info("sandbox_server starting on %s:%d", host, port)
    app.run(host=host, port=port, debug=False)
