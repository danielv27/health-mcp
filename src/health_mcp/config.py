"""Env-var settings. See PLAN.md "Access" for where these live on the VM."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HEALTH_MCP_", env_file=Path.home() / "health" / ".env"
    )

    db_path: Path = Path.home() / "health" / "health.db"
    hevy_api_key: str | None = None


settings = Settings()
