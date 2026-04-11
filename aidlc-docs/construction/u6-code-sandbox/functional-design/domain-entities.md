# U6 — Code Sandbox: Domain Entities

## SandboxResult
```
SandboxResult
  result   : Any | None        # Value assigned to `result` by user code
  stdout   : str               # Captured print() output
  error    : str | None        # Exception type + message, or None on success
```

## SandboxRequest (action_input parsed by Orchestrator)
```
SandboxRequest
  code      : str              # Python snippet (max 4096 chars)
  variables : dict[str, Any]   # Named inputs injected into the snippet's globals
```

## CodeSandbox (class in agent/execution/sandbox.py)
```
CodeSandbox
  +execute(code, variables, timeout=5.0) -> SandboxResult
  -_build_runner(code, variables)        -> str (temp file path)
  -_parse_output(raw_stdout)             -> SandboxResult
  -_log_execution(session_id, elapsed_ms, success, code_len)
```
