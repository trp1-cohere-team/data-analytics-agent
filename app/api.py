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

from agent.data_agent.config import AGENT_RUNTIME_EVENTS_PATH, TOOLS_YAML_PATH
from agent.data_agent.oracle_forge_agent import run_agent

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
EVENTS_PATH = ROOT / AGENT_RUNTIME_EVENTS_PATH
TOOLS_PATH = ROOT / TOOLS_YAML_PATH
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
        "available_db_tools": _load_available_tools(),
        "supported_db_hints": list(SUPPORTED_HINTS),
        "history_path": str(EVENTS_PATH),
    }


@app.get("/api/history")
def history() -> dict[str, Any]:
    return {"sessions": _load_history(limit=50)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
