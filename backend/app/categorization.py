"""Assigning each receipt one spending category."""

import logging

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMClient, LLMError
from app.models import Category, CategorySource, Receipt

logger = logging.getLogger(__name__)

CATEGORY_DESCRIPTIONS = {
    Category.GROCERIES: "supermarkets and food bought to cook at home",
    Category.DINING: "restaurants, cafés, bars, takeout, food delivery",
    Category.TRANSPORTATION: "fuel, rideshare, taxis, public transit, parking, tolls",
    Category.TRAVEL: "flights, hotels, car rental, travel bookings",
    Category.SHOPPING: "clothing, electronics, household goods, general retail",
    Category.UTILITIES: "electricity, water, gas, internet, phone bills",
    Category.HEALTH: "pharmacy, doctor, dentist, gym and fitness",
    Category.ENTERTAINMENT: "movies, concerts, events, games, hobbies",
    Category.SUBSCRIPTIONS: "recurring software, streaming, and memberships",
    Category.EDUCATION: "tuition, courses, textbooks, school supplies",
    Category.OFFICE: "office supplies, printing, postage, business services",
    Category.OTHER: "anything that doesn't fit the categories above",
}


class CategoryDecision(BaseModel):
    category: Category
    reason: str = Field(description="One short sentence explaining the choice.")


def build_category_prompt(receipt: Receipt) -> str:
    categories = "\n".join(f"- {c.value}: {desc}" for c, desc in CATEGORY_DESCRIPTIONS.items())
    items = "\n".join(f"  - {item.description}" for item in receipt.line_items) or "  (none)"
    return f"""\
Categorize this purchase for personal bookkeeping. Pick exactly one category.

Categories:
{categories}

Purchase:
Vendor: {receipt.vendor or "(unknown)"}
Total: {receipt.total if receipt.total is not None else "(unknown)"} {receipt.currency or ""}
Items:
{items}
"""


def assign_category(db: Session, llm: LLMClient, receipt: Receipt) -> None:
    """Reuse the category from an earlier receipt from the same vendor, else ask the LLM."""
    previous = _previous_category_for_vendor(db, receipt)
    if previous is not None:
        receipt.category = previous.category
        receipt.category_source = CategorySource.VENDOR_HISTORY
        receipt.category_reason = f"Same vendor as receipt #{previous.id}."
        return

    try:
        decision = llm.generate_structured(
            prompt=build_category_prompt(receipt), response_model=CategoryDecision
        )
    except LLMError:
        # Not fatal: the receipt is still saved, just uncategorized until someone sets it.
        logger.exception("Categorization failed for receipt %s", receipt.id)
        return
    receipt.category = decision.category
    receipt.category_source = CategorySource.LLM
    receipt.category_reason = decision.reason


def _previous_category_for_vendor(db: Session, receipt: Receipt) -> Receipt | None:
    """The most relevant earlier receipt from this vendor. Categories set by a person win."""
    if not receipt.vendor_key:
        return None
    query = (
        select(Receipt)
        .where(
            Receipt.vendor_key == receipt.vendor_key,
            Receipt.id != receipt.id,
            Receipt.category.is_not(None),
        )
        .order_by(
            (Receipt.category_source == CategorySource.USER).desc(),
            Receipt.created_at.desc(),
            Receipt.id.desc(),
        )
        .limit(1)
    )
    return db.scalars(query).first()
