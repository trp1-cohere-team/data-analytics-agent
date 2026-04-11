"""ProbeRunner — executes adversarial probes against the live agent.

ProbeRunner is a read-only observer: it calls the agent via HTTP and records
results but does NOT write to kb/corrections/, agent/memory/, or any
agent-internal state (PL-04).

Usage:
    python probes/probe_runner.py --agent-url http://localhost:8000
    python probes/probe_runner.py --agent-url http://localhost:8000 --category ROUTING
    python probes/probe_runner.py --agent-url http://localhost:8000 --probe-id JOIN_KEY-001
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

from agent.models import ProbeEntry, TraceStep

_PROBE_PASS_THRESHOLD = 0.8  # PL-06


# ---------------------------------------------------------------------------
# Probe loading from probes.md
# ---------------------------------------------------------------------------

def load_probes(path: str | Path = "probes/probes.md") -> list[ProbeEntry]:
    """Parse probes.md and return a list of ProbeEntry objects.

    Each probe block is a Markdown table with Field/Value rows.
    """
    content = Path(path).read_text(encoding="utf-8")

    probes: list[ProbeEntry] = []
    # Split on "---" separators between probe blocks
    blocks = re.split(r"\n---\n", content)

    for block in blocks:
        # Find table rows: | Field | Value |
        rows: dict[str, Any] = {}
        for line in block.splitlines():
            m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|", line)
            if m:
                key = m.group(1).strip().lower().replace(" ", "_")
                val: Any = m.group(2).strip()
                # Parse null / bool / list / float
                if val == "null":
                    val = None
                elif val == "true":
                    val = True
                elif val == "false":
                    val = False
                elif val.startswith("[") and val.endswith("]"):
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        pass
                else:
                    try:
                        val = float(val)
                        if val == int(val):
                            val = int(val)
                    except (ValueError, TypeError):
                        # Strip surrounding quotes if present
                        val = val.strip('"').strip("'")
                rows[key] = val

        if "id" in rows and "category" in rows and "query" in rows:
            try:
                probes.append(ProbeEntry(**rows))
            except Exception:
                pass  # Skip malformed blocks

    return probes


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def score_response(response: dict[str, Any], expected_failure_mode: str) -> float:
    """Score a pre-fix agent response against the expected failure mode.

    Returns 0.0–1.0. Pre-fix score should typically be low (failure expected).
    Scoring heuristic: if response contains error signals or empty answer → 0.0–0.3.
    """
    if not response:
        return 0.0
    answer = response.get("answer")
    confidence = float(response.get("confidence", 0.0))
    if answer is None or answer == "" or answer == []:
        return 0.0
    # Low confidence → low score
    if confidence < 0.3:
        return round(confidence, 2)
    # If answer is non-empty and confidence ok, treat as 0.5 pre-fix baseline
    return round(min(confidence, 0.5), 2)


def score_post_fix_response(response: dict[str, Any]) -> float:
    """Score a post-fix agent response. Higher is better."""
    if not response:
        return 0.0
    confidence = float(response.get("confidence", 0.0))
    answer = response.get("answer")
    if answer is None or answer == "" or answer == []:
        return 0.0
    return round(confidence, 2)


def extract_error_signal(query_trace: list[dict[str, Any]]) -> str | None:
    """Extract the first error observation from the query trace."""
    for step in query_trace:
        obs = step.get("observation", "")
        if "error" in obs.lower() or "failed" in obs.lower() or "exception" in obs.lower():
            return obs[:500]  # cap length
    return None


def count_correction_attempts(query_trace: list[dict[str, Any]]) -> int:
    """Count how many correction attempts appear in the trace."""
    return sum(
        1 for step in query_trace
        if "correct" in step.get("action", "").lower()
        or "retry" in step.get("action", "").lower()
    )


# ---------------------------------------------------------------------------
# HTTP call (stdlib only — no aiohttp dependency for probe runner)
# ---------------------------------------------------------------------------

def _call_agent(agent_url: str, question: str) -> dict[str, Any]:
    """POST a question to the agent and return the parsed response."""
    url = agent_url.rstrip("/") + "/query"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        return {"error": str(exc), "answer": None, "confidence": 0.0, "query_trace": []}
    except Exception as exc:
        return {"error": str(exc), "answer": None, "confidence": 0.0, "query_trace": []}


# ---------------------------------------------------------------------------
# Probe execution
# ---------------------------------------------------------------------------

def run_probe(probe: ProbeEntry, agent_url: str) -> ProbeEntry:
    """Execute one probe: pre-fix run → record → post-fix run → record.

    PL-04: ProbeRunner does NOT apply fixes. Fix is documented in probe.fix_applied.
    The caller is responsible for applying the fix between pre and post runs
    (or this function can be called separately for pre and post phases).
    """
    print(f"  Running probe {probe.id}: {probe.query[:60]}...")

    # Pre-fix run
    pre_response = _call_agent(agent_url, probe.query)
    trace = pre_response.get("query_trace", [])

    pre_score = score_response(pre_response, probe.expected_failure_mode)
    error_signal = extract_error_signal(trace)
    attempt_count = count_correction_attempts(trace)

    # Update probe with pre-fix results
    probe = probe.model_copy(update={
        "pre_fix_score": pre_score,
        "observed_agent_response": str(pre_response.get("answer", ""))[:500],
        "error_signal": error_signal,
        "correction_attempt_count": attempt_count,
    })

    print(f"    Pre-fix score: {pre_score:.2f}")
    print(f"    Fix to apply: {probe.fix_applied}")
    print(f"    (Apply fix manually, then run post-fix)")

    return probe


def run_post_fix(probe: ProbeEntry, agent_url: str) -> ProbeEntry:
    """Run a probe after fix has been applied and record post-fix score."""
    print(f"  Post-fix run for {probe.id}...")
    post_response = _call_agent(agent_url, probe.query)
    post_score = score_post_fix_response(post_response)
    passed = post_score >= _PROBE_PASS_THRESHOLD  # PL-06

    probe = probe.model_copy(update={
        "post_fix_score": post_score,
        "post_fix_pass": passed,
    })
    print(f"    Post-fix score: {post_score:.2f} → {'PASS' if passed else 'FAIL'}")
    return probe


def run_all(
    agent_url: str,
    category: str | None = None,
    probes_path: str | Path = "probes/probes.md",
) -> list[ProbeEntry]:
    """Run all probes (or all in a category) against the live agent.

    Only runs pre-fix phase. Post-fix requires manual fix application.
    """
    probes = load_probes(probes_path)
    if category:
        probes = [p for p in probes if p.category == category]

    print(f"\nRunning {len(probes)} probes against {agent_url}")
    results: list[ProbeEntry] = []
    for probe in probes:
        result = run_probe(probe, agent_url)
        results.append(result)
        time.sleep(0.5)  # rate-limit courtesy

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run adversarial probes against the Oracle Forge agent.")
    parser.add_argument("--agent-url", default="http://localhost:8000", help="Agent base URL")
    parser.add_argument("--category", help="Run only probes in this category (ROUTING|JOIN_KEY|TEXT_EXTRACT|DOMAIN_GAP)")
    parser.add_argument("--probe-id", help="Run a single probe by ID")
    parser.add_argument("--post-fix", action="store_true", help="Run post-fix scoring (assumes fix already applied)")
    parser.add_argument("--probes-path", default="probes/probes.md")
    args = parser.parse_args()

    probes = load_probes(args.probes_path)
    print(f"Loaded {len(probes)} probes from {args.probes_path}")

    if args.probe_id:
        probes = [p for p in probes if p.id == args.probe_id]
        if not probes:
            print(f"Probe {args.probe_id} not found.")
            sys.exit(1)

    if args.category:
        probes = [p for p in probes if p.category == args.category]

    for probe in probes:
        if args.post_fix:
            result = run_post_fix(probe, args.agent_url)
        else:
            result = run_probe(probe, args.agent_url)
        print(f"  {result.id}: pre={result.pre_fix_score} post={result.post_fix_score} pass={result.post_fix_pass}")


if __name__ == "__main__":
    main()
