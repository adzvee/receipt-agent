"""A cap on AI-backed requests for demo accounts, so a public demo can't exhaust the LLM quota."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User


def use_llm_request(db: Session, user: User) -> None:
    """Count one AI-backed request (an upload or a chat question) against a demo's limit.

    Regular accounts aren't limited here. The change is committed with the caller's work.
    """
    if not user.is_demo:
        return
    limit = get_settings().demo_llm_request_limit
    if user.llm_requests_used >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"The demo is limited to {limit} AI requests. Create a free account to keep going.",
        )
    user.llm_requests_used += 1
