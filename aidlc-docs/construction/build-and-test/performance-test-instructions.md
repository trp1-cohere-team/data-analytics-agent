# Performance Test Instructions — The Oracle Forge

**Date**: 2026-04-11

---

## Overview

Performance testing verifies that the system meets the NFR targets defined across units. No external load-testing tool (e.g. JMeter, k6) is required — performance targets are validated through the benchmark harness and timing assertions in integration tests.

---

## Performance Targets Summary

| Component | Target | Source |
|---|---|---|
| POST /query end-to-end (p50) | < 10s under normal LLM latency | PERF-U1-01 |
| ExactMatchScorer.score() | < 1 ms per call | PERF-U4-02 |
| LLMJudgeScorer.score() | < 30 s per call | PERF-U4-03 |
| ScoreLog.append() | < 5 ms | PERF-U4-04 |
| Full benchmark (50 queries × 1 trial) | ≤ 10 minutes | PERF-U4-01 |
| KnowledgeBase.load_documents() | < 2 s per subdirectory | PERF-U3-01 |

---

## Test 1: Single Query Latency

**Measures**: p50 and p95 latency of POST /query under normal conditions.

```bash
# Requires: agent + MCP Toolbox running
python - <<'EOF'
import asyncio, time, statistics, aiohttp

AGENT_URL = "http://localhost:8000"
QUESTION = "What is the total revenue across all databases?"
N = 20

async def one_call(session):
    t = time.monotonic()
    async with session.post(f"{AGENT_URL}/query", json={"question": QUESTION}) as r:
        await r.json()
    return (time.monotonic() - t) * 1000

async def main():
    async with aiohttp.ClientSession() as s:
        times = [await one_call(s) for _ in range(N)]
    times.sort()
    print(f"N={N}  p50={statistics.median(times):.0f}ms  p95={times[int(N*0.95)]:.0f}ms  max={max(times):.0f}ms")

asyncio.run(main())
EOF
```

**Expected**: p50 < 10,000 ms under normal OpenRouter latency.

---

## Test 2: ExactMatchScorer Throughput

**Measures**: That ExactMatchScorer stays under 1ms per call.

```bash
python - <<'EOF'
import time
from eval.harness import ExactMatchScorer

N = 10_000
cases = [("42", 42), ("hello", "hello"), ('[1,2]', [1, 2])]
t = time.monotonic()
for _ in range(N):
    for actual, expected in cases:
        ExactMatchScorer.score(actual, expected)
elapsed_ms = (time.monotonic() - t) * 1000
per_call_us = (elapsed_ms / (N * len(cases))) * 1000
print(f"{N * len(cases)} calls in {elapsed_ms:.1f}ms — {per_call_us:.2f}µs per call")
assert per_call_us < 1000, f"ExactMatchScorer too slow: {per_call_us:.0f}µs > 1000µs"
print("PASS: ExactMatchScorer < 1ms per call")
EOF
```

---

## Test 3: Full Benchmark Run Timing

**Measures**: Wall-clock time for a 50-query × 1-trial benchmark run.

```bash
# Requires: agent + MCP Toolbox running, DAB queries in signal/
time python -m eval.run_benchmark \
    --agent-url http://localhost:8000 \
    --trials 1 \
    --queries-path signal/
```

**Expected**: Completes in ≤ 10 minutes (600 seconds).  
`real` time in `time` output should be `< 10m0.000s`.

---

## Test 4: Rate Limiting Verification

**Measures**: That the 21st request in one minute receives 429 (slowapi enforcement).

```bash
python - <<'EOF'
import urllib.request, json, time

url = "http://localhost:8000/query"
body = json.dumps({"question": "test"}).encode()
headers = {"Content-Type": "application/json"}

for i in range(21):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            print(f"Request {i+1}: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"Request {i+1}: {e.code}")
        if i == 20:
            assert e.code == 429, f"Expected 429 on request 21, got {e.code}"
            print("PASS: Rate limit 429 on request 21")
EOF
```

---

## Performance Optimization Guidance

If targets are not met:

| Symptom | Likely Cause | Fix |
|---|---|---|
| p50 query > 10s | OpenRouter latency high | Switch to faster model in `OPENROUTER_MODEL` |
| Benchmark > 10 min | Agent calls taking > 10s each | Increase `_AGENT_CONCURRENCY` or reduce `n_trials` |
| ExactMatch > 1ms | Python startup overhead in test harness | Warm up with one call before timing |
| 429 not returned at 21 | slowapi misconfigured | Check `RATE_LIMIT` setting in config |
