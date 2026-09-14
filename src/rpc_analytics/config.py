"""Service configuration from environment (trusted project identity)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment-fixed settings. Project identity never comes from clients."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_id: str = Field(default="rekordbox-playlist-converter", alias="PROJECT_ID")
    project_name: str = Field(default="Rekordbox Playlist Converter", alias="PROJECT_NAME")
    sqlite_path: str = Field(default="/data/analytics.db", alias="SQLITE_PATH")
    report_token: str = Field(default="", alias="REPORT_TOKEN")
    rate_limit_capacity: float = Field(default=30.0, alias="RATE_LIMIT_CAPACITY")
    rate_limit_refill_per_second: float = Field(default=0.5, alias="RATE_LIMIT_REFILL_PER_SECOND")
    rate_limit_salt_seed: str = Field(default="rpc-analytics-default-salt", alias="RATE_LIMIT_SALT_SEED")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8091, alias="PORT")
    max_body_bytes: int = 4096


@lru_cache
def get_settings() -> Settings:
    return Settings()
