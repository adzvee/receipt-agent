"""Application settings, loaded from environment variables (or the repo-root .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://receipts:receipts@localhost:5433/receipts"

    # LLM
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # Uploaded receipt files
    storage_dir: Path = REPO_ROOT / "storage"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Postmark inbound webhook (HTTP Basic Auth). Leave empty to disable the endpoint.
    postmark_inbound_username: str = ""
    postmark_inbound_password: str = ""
    # Your Postmark inbound address, e.g. "abc123@inbound.postmarkapp.com". Each user
    # forwards to "abc123+<their token>@inbound.postmarkapp.com".
    postmark_inbound_address: str = ""

    # Accounts
    jwt_secret: str = ""  # required outside development; see app/auth.py
    access_token_minutes: int = 24 * 60
    demo_ttl_hours: int = 24
    demo_llm_request_limit: int = 25  # AI-backed uploads + chat questions per demo account


@lru_cache
def get_settings() -> Settings:
    return Settings()
