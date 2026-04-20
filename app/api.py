from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.data_agent.config import AGENT_OFFLINE_MODE, AGENT_RUNTIME_EVENTS_PATH, TOOLS_YAML_PATH
from agent.data_agent.oracle_forge_agent import run_agent

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
EVENTS_PATH = ROOT / AGENT_RUNTIME_EVENTS_PATH
TOOLS_PATH = ROOT / TOOLS_YAML_PATH
RESULTS_DIR = ROOT / "results"
PROBES_PATH = ROOT / "probes" / "probes.md"
SCORE_PROGRESSION_PATH = RESULTS_DIR / "score_progression.jsonl"
BENCHMARK_RESULTS_PATH = RESULTS_DIR / "dab_benchmark_5trials.json"
SUPPORTED_HINTS = ("sqlite", "duckdb", "postgresql", "mongodb")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4096)
    db_hints: list[str] = Field(default_factory=list, max_length=10)


app = FastAPI(title="OracleForge Data Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _load_available_tools() -> list[dict[str, Any]]:
    if not TOOLS_PATH.is_file():
        return []
    try:
        data = yaml.safe_load(TOOLS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []

    tools = data.get("tools", {})
    items: list[dict[str, Any]] = []
    for name, meta in tools.items():
        items.append(
            {
                "name": name,
                "kind": meta.get("kind", ""),
                "source": meta.get("source", ""),
                "description": meta.get("description", ""),
            }
        )
    return items


def _load_history(limit: int = 50) -> list[dict[str, Any]]:
    if not EVENTS_PATH.is_file():
        return []

    sessions: dict[str, dict[str, Any]] = {}
    try:
        with EVENTS_PATH.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                session_id = str(event.get("session_id", "")).strip()
                if not session_id:
                    continue

                record = sessions.setdefault(
                    session_id,
                    {
                        "session_id": session_id,
                        "question": "",
                        "answer": "",
                        "confidence": 0.0,
                        "timestamp": "",
                        "trace_id": "",
                    },
                )
                event_type = event.get("event_type")
                extra = event.get("extra") or {}

                if event_type == "question_received":
                    record["question"] = event.get("input_summary", "") or record["question"]
                elif event_type == "session_end":
                    record["answer"] = extra.get("answer_preview", "") or record["answer"]
                    record["confidence"] = float(extra.get("confidence", record["confidence"]) or 0.0)
                    record["trace_id"] = extra.get("trace_id", "") or record["trace_id"]
                    record["timestamp"] = event.get("timestamp", "") or record["timestamp"]
    except OSError:
        return []

    history = list(sessions.values())
    history.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return history[:limit]


def _load_eval_summary() -> dict[str, Any]:
    summary = {
        "pass_at_1": 0.0,
        "total_entries": 0,
        "passed_entries": 0,
        "avg_confidence": 0.0,
        "latest_scored_at": "",
    }

    if BENCHMARK_RESULTS_PATH.is_file():
        try:
            payload = json.loads(BENCHMARK_RESULTS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                total = len(payload)
                passed = sum(1 for row in payload if isinstance(row, dict) and row.get("pass"))
                confidences = [
                    float(row.get("confidence", 0.0))
                    for row in payload
                    if isinstance(row, dict) and row.get("confidence") is not None
                ]
                summary["total_entries"] = total
                summary["passed_entries"] = passed
                summary["pass_at_1"] = round(passed / total, 4) if total else 0.0
                summary["avg_confidence"] = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass

    if SCORE_PROGRESSION_PATH.is_file():
        try:
            latest: dict[str, Any] | None = None
            with SCORE_PROGRESSION_PATH.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if isinstance(row, dict):
                        latest = row
            if latest:
                summary["latest_scored_at"] = str(latest.get("timestamp_utc", ""))
                if latest.get("pass_at_1") is not None:
                    summary["pass_at_1"] = float(latest.get("pass_at_1") or summary["pass_at_1"])
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass

    return summary


def _load_probe_summary() -> dict[str, Any]:
    summary = {"total_probes": 0, "categories": 0}
    if not PROBES_PATH.is_file():
        return summary

    try:
        text = PROBES_PATH.read_text(encoding="utf-8")
    except OSError:
        return summary

    summary["total_probes"] = sum(1 for line in text.splitlines() if line.startswith("### Probe "))
    summary["categories"] = sum(
        1 for line in text.splitlines() if line.startswith("## Category ")
    )
    return summary


@app.post("/api/chat")
def chat(payload: ChatRequest) -> JSONResponse:
    result = run_agent(payload.question, payload.db_hints)
    return JSONResponse(asdict(result))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "oracleforge-data-agent",
        "port": 8501,
        "offline_mode": AGENT_OFFLINE_MODE,
        "available_db_tools": _load_available_tools(),
        "supported_db_hints": list(SUPPORTED_HINTS),
        "history_path": str(EVENTS_PATH),
    }


@app.get("/api/history")
def history() -> dict[str, Any]:
    return {"sessions": _load_history(limit=50)}


@app.get("/api/dashboard_summary")
def dashboard_summary() -> dict[str, Any]:
    return {
        "eval": _load_eval_summary(),
        "probes": _load_probe_summary(),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
