# U6 — Code Sandbox: Functional Design Plan

**Unit**: U6 — Code Sandbox Execution Layer  
**Build Order**: 6th (after all original units)  
**Purpose**: Execute transformation code for unstructured text extraction and return result + validation status, as shown in the architecture diagram alongside MCP Toolbox.

---

## What the Code Sandbox does

The Code Sandbox is a second execution path in the Orchestrator's `act()` step. When the agent decides it needs to transform or extract information from unstructured text (e.g., parse a MongoDB document, reshape nested JSON, compute a derived field), instead of calling a DB tool it calls the sandbox with a small Python snippet. The sandbox runs it safely and returns the result.

```
Orchestrator act()
  ├── query_database  →  MCP Toolbox  →  PostgreSQL/MongoDB/DuckDB/SQLite
  └── run_code        →  Code Sandbox →  Python execution result + validation
```

---

## Functional Design Questions

Please answer all questions using `[Answer]: <letter>` tags.

---

### Q1 — Execution Backend
How should Python snippets be executed?

A) `subprocess` with a timeout — run in a child process, killed after N seconds  
B) `RestrictedPython` — compile-time AST restriction, no subprocess needed  
C) `exec()` inside an isolated `dict` namespace — simplest, no extra dependencies  
D) Docker container per call — strongest isolation, requires Docker on the server

[Answer]: A

---

### Q2 — Allowed Operations
What should the sandbox allow the code to do?

A) Pure computation only — string manipulation, list ops, math, JSON parsing. No imports.  
B) Allow a whitelist of safe stdlib imports: `json`, `re`, `math`, `datetime`, `collections`  
C) Allow any import except network and filesystem writes  
D) No restrictions — trust the agent fully

[Answer]: B

---

### Q3 — Timeout
How long should the sandbox wait before killing execution?

A) 2 seconds  
B) 5 seconds  
C) 10 seconds  
D) 30 seconds

[Answer]: B

---

### Q4 — Input Format
What does the agent pass to the sandbox?

A) A Python code string + a `data` variable pre-bound to the observation from the previous DB call  
B) A Python code string only — agent must embed any data it needs as literals in the code  
C) A Python code string + arbitrary named variables dict (agent names the inputs)

[Answer]: C

---

### Q5 — Output Format
What does the sandbox return to the orchestrator?

A) `{"result": <any JSON-serialisable value>, "stdout": "<captured print output>", "error": null}`  
B) `{"result": <value>, "error": "<error message or null>"}` — no stdout capture  
C) Plain string — the agent interprets it

[Answer]: A

---

### Q6 — Where does sandbox live?
Which module should own the sandbox?

A) New file: `agent/execution/sandbox.py` alongside the existing `engine.py` and `mcp_client.py`  
B) New top-level module: `sandbox/executor.py`  
C) Inside `utils/` as a utility: `utils/code_executor.py`

[Answer]: A

---

### Q7 — New Orchestrator action name
What action name should the agent use in its ReAct JSON to invoke the sandbox?

A) `run_code`  
B) `execute_code`  
C) `sandbox`  
D) `transform_data`

[Answer]: D

---

### Q8 — Security logging
Should sandbox executions be logged?

A) Yes — log `session_id`, `elapsed_ms`, `success/fail`, code length in chars. Never log code content (same rule as queries).  
B) Yes — log everything including the code string  
C) No logging

[Answer]: A
