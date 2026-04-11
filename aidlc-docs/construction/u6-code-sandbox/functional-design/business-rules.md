# U6 — Code Sandbox: Business Rules

## BR-U6-01: Code length limit
User code must not exceed 4096 characters. Reject immediately with `ValidationError` — no subprocess spawned.

## BR-U6-02: Variables must be JSON-serialisable
All values in the variables dict must survive `json.dumps()`. Reject non-serialisable inputs before spawning a subprocess.

## BR-U6-03: Timeout = 5 seconds hard kill
`subprocess.run(..., timeout=5.0)` kills the child process on expiry. Return `SandboxResult(result=None, stdout="", error="TimeoutExpired")`.

## BR-U6-04: Temp file always cleaned up
Use `try/finally` to delete the temp runner file regardless of success, timeout, or exception.

## BR-U6-05: Security logging — metadata only
Log: `session_id`, `elapsed_ms`, `success` (bool), `code_len` (int). Never log code content or variable values.

## BR-U6-06: result must be assigned
If user code does not assign `result`, the JSON output contains `"result": null`. This is not an error — the orchestrator treats it as an empty observation.

## BR-U6-07: No network calls possible
The subprocess inherits no special environment. No `requests`, `httpx`, `socket`, or `urllib` are importable (not in whitelist). This is enforced by the import whitelist in the runner script.

## BR-U6-08: Orchestrator action name is `transform_data`
The ReAct JSON `{"action": "transform_data", "action_input": {"code": "...", "variables": {...}}}` is the only trigger. Any other spelling falls through to the existing unknown-action handler.
