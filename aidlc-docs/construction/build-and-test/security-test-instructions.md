# Security Test Instructions — The Oracle Forge

**Date**: 2026-04-11  
**Extension**: Security Baseline (blocking, all 15 rules enforced)

---

## Overview

Security tests validate that all 15 Security Baseline rules are enforced. Tests are grouped by unit and cover header enforcement, error sanitization, log content, injection prevention, and dependency safety.

---

## Test 1: Security Headers (SEC-U1-02)

**Verifies**: X-Content-Type-Options, X-Frame-Options, CSP present on all responses.

```bash
# Requires: agent running
curl -sI http://localhost:8000/health | grep -E "x-content-type|x-frame|content-security"
```

**Expected output** (all three lines present):
```
x-content-type-options: nosniff
x-frame-options: DENY
content-security-policy: default-src 'none'
```

Also verified by unit tests: `tests/unit/test_api.py::TestSecurityHeaders`

---

## Test 2: Error Sanitization (SEC-U1-03)

**Verifies**: 500 responses expose only exception class name, not stack traces or internal details.

```bash
# Unit test covers this scenario:
pytest tests/unit/test_api.py::TestErrorSanitization -v
```

**Manual check**:
```bash
# Trigger a 500 (send malformed JSON beyond validation)
curl -s -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "x"}' | python -m json.tool
# body["message"] must NOT contain stack traces or internal paths
```

---

## Test 3: No Content in Logs (SEC-U1-01, SEC-U4-01)

**Verifies**: Query text and agent answers never appear in log output.

```bash
# Run a query while capturing logs
uvicorn agent.api.app:app --port 8000 --log-level debug 2>agent.log &
curl -s -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "SENTINEL_SECRET_QUERY_TEXT"}' > /dev/null

grep "SENTINEL_SECRET_QUERY_TEXT" agent.log
```

**Expected**: No matches. Log must not contain query text.

---

## Test 4: Rate Limiting (SEC-U1-01 / FR-05)

**Verifies**: 21st request in a minute receives HTTP 429.

```bash
# See performance-test-instructions.md Test 4 for the full script
pytest tests/unit/test_api.py -v -k "rate_limit"
```

---

## Test 5: Score Log Append-Only (SEC-U4-02)

**Verifies**: `score_log.jsonl` is never opened in write/truncate mode.

```bash
# Automated by PBT-U4-02 round-trip test
pytest tests/unit/test_harness.py::test_score_log_round_trip -v

# Manual check: run benchmark twice; log must have 2 lines
python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 1
python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 1
wc -l results/score_log.jsonl
# Expected: 2
```

---

## Test 6: Dependency Vulnerability Scan

**Verifies**: No known CVEs in installed packages.

```bash
pip install safety
safety check -r requirements.txt
```

**Expected**: `No known security vulnerabilities found.`  
Run weekly in CI per Security Baseline requirements.

---

## Test 7: Trace File Write-Once (SEC-U4-04)

**Verifies**: Writing the same trace twice raises `ValueError`.

```bash
pytest tests/unit/test_harness.py -v -k "trace"
```

**Expected**: The write-once guard test passes (no silently overwritten traces).

---

## Test 8: KB FilenameGuard (SEC-U3-01)

**Verifies**: Only `^[\w\-.]+\.md$` filenames are accepted in KB injection.

```bash
pytest tests/unit/test_knowledge_base.py -v -k "filename"
```

---

## Test 9: No API Key in Traces or Logs

**Verifies**: `OPENROUTER_API_KEY` value never appears in output files.

```bash
# Run a benchmark
python -m eval.run_benchmark --agent-url http://localhost:8000 --trials 1

# Search for the key value in all output files
grep -r "$OPENROUTER_API_KEY" results/ agent/memory/ kb/
```

**Expected**: No matches.

---

## Security Test Checklist

| Test | Method | Status |
|---|---|---|
| Security headers on all responses | Unit test + curl | To verify |
| Error sanitization (500 shows type only) | Unit test | To verify |
| No query content in logs | Manual grep | To verify |
| Rate limiting (429 at 21 req/min) | Unit test | To verify |
| Score log append-only | PBT + manual wc | To verify |
| Dependency CVE scan | `safety check` | To verify |
| Trace write-once guard | Unit test | To verify |
| KB filename guard | Unit test | To verify |
| API key not in output files | grep scan | To verify |
