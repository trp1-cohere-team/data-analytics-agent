# U6 — Code Sandbox: Business Logic Model

## Execution Flow

```
Orchestrator.act()
  └── action == "transform_data"
        │
        ▼
  CodeSandbox.execute(code, variables, timeout=5.0)
        │
        ├── 1. Validate code length (max 4096 chars)
        ├── 2. Validate variables are JSON-serialisable
        ├── 3. Build runner script (inject variables + user code)
        ├── 4. Write runner to temp file
        ├── 5. subprocess.run([python, temp_file], timeout=5.0, capture_output=True)
        ├── 6. Parse stdout as JSON → SandboxResult
        └── 7. Clean up temp file (always)
        │
        ▼
  SandboxResult(result, stdout, error)
        │
        ▼
  Orchestrator.act() → Observation(content=result_json, success=(error is None))
```

## Runner Script Template

The sandbox writes and executes this script in a child process:

```python
import sys, json, io, traceback

# Inject variables (serialised by sandbox, deserialised here)
_vars = json.loads("""<VARS_JSON>""")
for _k, _v in _vars.items():
    globals()[_k] = _v

# Whitelist imports only
import json, re, math, datetime, collections

_stdout_buf = io.StringIO()
_result = None
_error = None

try:
    import sys as _sys
    _sys.stdout = _stdout_buf
    # --- USER CODE START ---
    <USER_CODE>
    # --- USER CODE END ---
    _sys.stdout = sys.__stdout__
except Exception as _exc:
    _sys.stdout = sys.__stdout__
    _error = type(_exc).__name__ + ": " + str(_exc)

print(json.dumps({
    "result": _result,
    "stdout": _stdout_buf.getvalue(),
    "error": _error,
}))
```

## Allowed Imports

The runner script pre-imports only these modules before running user code:

| Module | Purpose |
|--------|---------|
| `json` | Parse/format JSON data |
| `re` | Regular expressions for text extraction |
| `math` | Numeric computations |
| `datetime` | Date/time parsing and formatting |
| `collections` | Counter, defaultdict, OrderedDict |

Any `import` statement in user code that is NOT in this list will raise `ImportError` because the subprocess has no additional packages and `sys.path` is not extended.

## Variables Contract

- Agent provides: `{"variable_name": <JSON-serialisable value>, ...}`
- All values must be JSON-serialisable (str, int, float, list, dict, bool, None)
- Variables are injected into the runner's global namespace before user code runs
- `result` must be assigned by user code — it is the primary output

## Error Taxonomy

| Scenario | `error` field | `result` field |
|----------|---------------|----------------|
| Success | `null` | Any JSON value |
| Timeout | `"TimeoutExpired"` | `null` |
| SyntaxError in code | `"SyntaxError: ..."` | `null` |
| Import not in whitelist | `"ImportError: ..."` | `null` |
| Runtime exception | `"ExceptionType: message"` | `null` |
| Code too long | `"ValidationError: code exceeds 4096 chars"` | `null` |
