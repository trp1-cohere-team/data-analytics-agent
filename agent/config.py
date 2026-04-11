"""Central configuration for The Oracle Forge agent.

All units import the singleton `settings` from this module.
Never read os.environ directly in application code — use settings instead.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"

    # MCP Toolbox
    mcp_toolbox_url: str = "http://localhost:5000"

    # Agent server
    agent_port: int = 8000
    rate_limit: str = "20/minute"

    # ReAct loop
    max_react_iterations: int = 10
    confidence_threshold: float = 0.85

    # Correction engine
    max_correction_attempts: int = 3

    # Context layers
    layer2_refresh_interval_s: int = 60
    corrections_limit: int = 50

    # Memory
    memory_max_age_days: int = 7

    # Paths
    kb_dir: Path = Path("kb")
    memory_dir: Path = Path("agent/memory")
    results_dir: Path = Path("results")

    # SchemaIntrospector timeouts (seconds)
    outer_introspect_timeout: float = 9.0
    db_timeout_mongodb: float = 4.0
    db_timeout_postgres: float = 2.5
    db_timeout_duckdb: float = 1.5
    db_timeout_sqlite: float = 1.0

    @property
    def db_timeouts(self) -> dict[str, float]:
        """Per-DB sub-limits for SchemaIntrospector bulkhead."""
        return {
            "mongodb": self.db_timeout_mongodb,
            "postgres": self.db_timeout_postgres,
            "duckdb": self.db_timeout_duckdb,
            "sqlite": self.db_timeout_sqlite,
        }


settings = Settings()
