from __future__ import annotations

import os
import re
from dataclasses import dataclass


def _load_local_env(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file."""
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                # Ignore malformed env keys.
                continue
            if key and key not in os.environ:
                os.environ[key] = value


_load_local_env()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AgentConfig:
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_model: str = os.getenv(
        "OPENROUTER_MODEL", os.getenv("MODEL", "openai/gpt-4.1-mini")
    )
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    app_name: str = os.getenv("OPENROUTER_APP_NAME", "oracle-forge-agent")
    max_tokens: int = int(os.getenv("AGENT_MAX_TOKENS", "700"))
    temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.1"))
    timeout_seconds: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "45"))
    offline_mode: bool = _env_bool("AGENT_OFFLINE_MODE", True)
    use_mcp: bool = _env_bool("AGENT_USE_MCP", True)
    mcp_base_url: str = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000")
    mcp_timeout_seconds: int = int(os.getenv("MCP_TIMEOUT_SECONDS", "8"))
    use_sandbox: bool = _env_bool("AGENT_USE_SANDBOX", False)
    sandbox_url: str = os.getenv("SANDBOX_URL", "http://localhost:8080")
    sandbox_timeout_seconds: int = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "12"))
    duckdb_path: str = os.getenv("DUCKDB_PATH", "./data/duckdb/main.duckdb")
    self_correction_retries: int = int(os.getenv("AGENT_SELF_CORRECTION_RETRIES", "1"))
    max_execution_steps: int = int(os.getenv("AGENT_MAX_EXECUTION_STEPS", "6"))
    memory_root_dir: str = os.getenv("AGENT_MEMORY_ROOT", ".oracle_forge_memory")
    runtime_events_path: str = os.getenv(
        "AGENT_RUNTIME_EVENTS_PATH", ".oracle_forge_memory/events.jsonl"
    )
    corrections_log_path: str = os.getenv(
        "AGENT_CORRECTIONS_LOG_PATH", "kb/corrections/corrections_log.md"
    )
    agent_context_path: str = os.getenv("AGENT_CONTEXT_PATH", "agent/AGENT.md")
    memory_max_session_items: int = int(os.getenv("AGENT_MEMORY_SESSION_ITEMS", "12"))
    memory_max_topic_chars: int = int(os.getenv("AGENT_MEMORY_TOPIC_CHARS", "2500"))
    session_id: str | None = os.getenv("AGENT_SESSION_ID")


CONFIG = AgentConfig()
