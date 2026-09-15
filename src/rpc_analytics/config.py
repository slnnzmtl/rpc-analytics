"""Service configuration from environment (trusted project identity)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment-fixed settings. Project identity never comes from clients."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_id: str = Field(default="rekordbox-playlist-converter", alias="PROJECT_ID")
    project_name: str = Field(default="Rekordbox Playlist Converter", alias="PROJECT_NAME")
    sqlite_path: str = Field(default="/data/analytics.db", alias="SQLITE_PATH")
    report_token: str = Field(default="", alias="REPORT_TOKEN")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    # Comma-separated emails (not JSON); keep as str so env parsing stays simple.
    dashboard_allowed_emails: str = Field(
        default="slonanezametil@gmail.com",
        alias="DASHBOARD_ALLOWED_EMAILS",
    )
    rate_limit_capacity: float = Field(default=30.0, alias="RATE_LIMIT_CAPACITY")
    rate_limit_refill_per_second: float = Field(default=0.5, alias="RATE_LIMIT_REFILL_PER_SECOND")
    rate_limit_salt_seed: str = Field(default="rpc-analytics-default-salt", alias="RATE_LIMIT_SALT_SEED")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8091, alias="PORT")
    max_body_bytes: int = 4096

    @field_validator("dashboard_allowed_emails", mode="before")
    @classmethod
    def normalize_allowed_emails(cls, value: object) -> str:
        if value is None or value == "":
            return "slonanezametil@gmail.com"
        if isinstance(value, list):
            return ",".join(str(item).strip() for item in value if str(item).strip())
        return str(value)

    def allowed_email_set(self) -> set[str]:
        return {
            part.strip().lower()
            for part in self.dashboard_allowed_emails.split(",")
            if part.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
