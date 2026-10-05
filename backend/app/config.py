"""Application settings, loaded from environment variables (or the repo-root .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://receipts:receipts@localhost:5433/receipts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
