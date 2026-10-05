"""Aggregates for the dashboard."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.agent.tools import SpendingSummaryArgs, spending_summary
from app.db import DbSession

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/spending")
def get_spending(args: Annotated[SpendingSummaryArgs, Query()], db: DbSession) -> dict[str, Any]:
    """Spending totals, e.g. `?group_by=category&start_date=2026-09-01`.

    Uses the same function as the Q&A agent's `spending_summary` tool, so the dashboard
    and the chat always agree.
    """
    return spending_summary(db, args)
