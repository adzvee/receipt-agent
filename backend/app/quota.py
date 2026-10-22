"""Limits on AI-backed work, so no single account can use up the shared LLM quota.

- Every account: a few receipts and chat questions per (UTC) day.
- Demo accounts: also a total cap for the account's lifetime.
"""

from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DailyUsage, UsageKind, User

LIMIT_MESSAGES = {
    UsageKind.RECEIPTS: "You've added today's limit of {limit} receipts.",
    UsageKind.QUESTIONS: "You've asked today's limit of {limit} questions.",
}


def utc_today() -> date:
    return datetime.now(UTC).date()


def daily_limit(kind: UsageKind) -> int:
    settings = get_settings()
    return {
        UsageKind.RECEIPTS: settings.daily_receipt_limit,
        UsageKind.QUESTIONS: settings.daily_question_limit,
    }[kind]


def used_today(db: Session, user: User, kind: UsageKind, today: date | None = None) -> int:
    count = db.scalar(
        select(DailyUsage.count).where(
            DailyUsage.user_id == user.id,
            DailyUsage.day == (today or utc_today()),
            DailyUsage.kind == kind,
        )
    )
    return count or 0


def left_today(db: Session, user: User, kind: UsageKind, today: date | None = None) -> int:
    return max(daily_limit(kind) - used_today(db, user, kind, today), 0)


def try_use_daily(db: Session, user: User, kind: UsageKind, today: date | None = None) -> bool:
    """Count one use if the account is under today's limit. Returns False if it isn't.

    One INSERT ... ON CONFLICT UPDATE that only increments while under the limit, so two
    requests at the same moment can't both slip through. It's committed (or rolled back)
    with the caller's work.
    """
    added = (
        insert(DailyUsage)
        .values(user_id=user.id, day=today or utc_today(), kind=kind, count=1)
        .on_conflict_do_update(
            index_elements=["user_id", "day", "kind"],
            set_={"count": DailyUsage.count + 1},
            where=DailyUsage.count < daily_limit(kind),
        )
        .returning(DailyUsage.count)
    )
    return db.scalar(added) is not None  # no row back: the update's condition failed


def use_daily(db: Session, user: User, kind: UsageKind) -> None:
    """Like `try_use_daily`, but answers the HTTP request with a 429 when over the limit."""
    if not try_use_daily(db, user, kind):
        message = LIMIT_MESSAGES[kind].format(limit=daily_limit(kind))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, f"{message} It resets at midnight UTC."
        )


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
