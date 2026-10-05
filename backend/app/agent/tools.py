"""The read-only database tools the Q&A agent can call.

The LLM never writes SQL. It can only pick one of these tools and fill in its arguments,
which are validated against a Pydantic model before any query runs. Each tool is a fixed,
parameterized SQLAlchemy SELECT.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.llm import ToolCall, ToolSpec
from app.models import Category, FlagKind, LineItem, Receipt, ReceiptFlag, ReceiptStatus

COUNTED_NOTE = "Totals exclude receipts that couldn't be read and receipts flagged as duplicates."


# --- Arguments the model can pass ---


class ReceiptFilters(BaseModel):
    start_date: date | None = Field(None, description="First purchase date to include.")
    end_date: date | None = Field(None, description="Last purchase date to include (inclusive).")
    categories: list[Category] | None = Field(None, description="Only these categories.")
    vendor: str | None = Field(None, description="Only vendors whose name contains this text.")


class SpendingSummaryArgs(ReceiptFilters):
    group_by: Literal["none", "category", "vendor", "month"] = Field(
        "none", description="Break the total down by this field."
    )


class ListReceiptsArgs(ReceiptFilters):
    min_total: float | None = Field(None, description="Only receipts with at least this total.")
    needs_review: bool | None = Field(
        None, description="true: only receipts with open flags. false: only unflagged ones."
    )
    sort: Literal["newest", "oldest", "largest"] = "newest"
    limit: int = Field(10, ge=1, le=25)


class GetReceiptArgs(BaseModel):
    receipt_id: int


class SearchLineItemsArgs(BaseModel):
    text: str = Field(min_length=1, max_length=100, description="Words to find in item names.")
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(20, ge=1, le=50)


# --- Query helpers ---


def _is_counted() -> Any:
    """Receipts that count toward spending: read successfully, and not an open duplicate."""
    open_duplicate = Receipt.flags.any(
        and_(ReceiptFlag.kind == FlagKind.DUPLICATE, ReceiptFlag.dismissed_at.is_(None))
    )
    return and_(
        Receipt.status == ReceiptStatus.EXTRACTED, Receipt.total.is_not(None), ~open_duplicate
    )


def _contains(column: Any, text: str) -> Any:
    """Case-insensitive "contains", treating % and _ in the user's text literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _apply_date_range(query: Select, start: date | None, end: date | None) -> Select:
    if start is not None:
        query = query.where(Receipt.purchase_date >= start)
    if end is not None:
        query = query.where(Receipt.purchase_date <= end)
    return query


def _apply_filters(query: Select, filters: ReceiptFilters) -> Select:
    query = _apply_date_range(query, filters.start_date, filters.end_date)
    if filters.categories:
        query = query.where(Receipt.category.in_(filters.categories))
    if filters.vendor:
        query = query.where(_contains(Receipt.vendor, filters.vendor))
    return query


def _receipt_summary(receipt: Receipt) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "date": receipt.purchase_date.isoformat() if receipt.purchase_date else None,
        "vendor": receipt.vendor,
        "total": str(receipt.total) if receipt.total is not None else None,
        "currency": receipt.currency,
        "category": receipt.category.value if receipt.category else None,
        "open_flags": [f.code for f in receipt.flags if f.dismissed_at is None],
    }


# --- The tools ---


def spending_summary(db: Session, args: SpendingSummaryArgs) -> dict[str, Any]:
    # For each grouping: (what to display, what to group by).
    month = func.to_char(Receipt.purchase_date, "YYYY-MM")
    group_label, group_key = {
        "none": (None, None),
        "category": (Receipt.category, Receipt.category),
        # Group by normalized vendor so "STARBUCKS #12" and "Starbucks" are one row.
        "vendor": (func.min(Receipt.vendor), Receipt.vendor_key),
        "month": (month, month),
    }[args.group_by]

    total = func.sum(Receipt.total)
    columns = [Receipt.currency, total.label("total"), func.count(Receipt.id).label("count")]
    query = select(*columns).where(_is_counted()).group_by(Receipt.currency)
    if group_label is not None:
        query = query.add_columns(group_label.label("group")).group_by(group_key)
    query = _apply_filters(query, args).order_by(total.desc()).limit(50)

    groups = []
    for row in db.execute(query):
        group = {"currency": row.currency, "total": str(row.total), "receipt_count": row.count}
        if group_label is not None:
            group = {args.group_by: str(row.group) if row.group else "(none)", **group}
        groups.append(group)
    return {"groups": groups, "note": COUNTED_NOTE}


def list_receipts(db: Session, args: ListReceiptsArgs) -> dict[str, Any]:
    order = {
        "newest": (Receipt.purchase_date.desc().nulls_last(), Receipt.id.desc()),
        "oldest": (Receipt.purchase_date.asc().nulls_last(), Receipt.id.asc()),
        "largest": (Receipt.total.desc().nulls_last(), Receipt.id.desc()),
    }[args.sort]
    query = _apply_filters(select(Receipt), args).order_by(*order)
    if args.min_total is not None:
        query = query.where(Receipt.total >= args.min_total)
    if args.needs_review is not None:
        has_open_flag = Receipt.flags.any(ReceiptFlag.dismissed_at.is_(None))
        query = query.where(has_open_flag if args.needs_review else ~has_open_flag)

    receipts = list(db.scalars(query.limit(args.limit + 1)))
    return {
        "receipts": [_receipt_summary(r) for r in receipts[: args.limit]],
        "more_results": len(receipts) > args.limit,
    }


def get_receipt(db: Session, args: GetReceiptArgs) -> dict[str, Any]:
    receipt = db.get(Receipt, args.receipt_id)
    if receipt is None:
        return {"error": f"There is no receipt #{args.receipt_id}."}
    return {
        **_receipt_summary(receipt),
        "status": receipt.status.value,
        "subtotal": str(receipt.subtotal) if receipt.subtotal is not None else None,
        "tax": str(receipt.tax) if receipt.tax is not None else None,
        "tip": str(receipt.tip) if receipt.tip is not None else None,
        "payment_method": receipt.payment_method,
        "line_items": [
            {"description": item.description, "amount": str(item.amount)}
            for item in receipt.line_items
        ],
        "flags": [
            {"code": f.code, "message": f.message, "dismissed": f.dismissed_at is not None}
            for f in receipt.flags
        ],
    }


def search_line_items(db: Session, args: SearchLineItemsArgs) -> dict[str, Any]:
    def matching(query: Select) -> Select:
        query = query.join(Receipt).where(_is_counted(), _contains(LineItem.description, args.text))
        return _apply_date_range(query, args.start_date, args.end_date)

    rows = db.execute(
        matching(select(LineItem, Receipt))
        .order_by(Receipt.purchase_date.desc().nulls_last(), LineItem.id)
        .limit(args.limit + 1)
    ).all()
    totals = db.execute(
        matching(
            select(Receipt.currency, func.sum(LineItem.amount), func.count(LineItem.id))
        ).group_by(Receipt.currency)
    ).all()
    return {
        "matches": [
            {
                "receipt_id": receipt.id,
                "date": receipt.purchase_date.isoformat() if receipt.purchase_date else None,
                "vendor": receipt.vendor,
                "description": item.description,
                "amount": str(item.amount),
                "currency": receipt.currency,
            }
            for item, receipt in rows[: args.limit]
        ],
        "more_results": len(rows) > args.limit,
        "totals": [
            {"currency": currency, "total": str(total), "item_count": count}
            for currency, total, count in totals
        ],
        "note": COUNTED_NOTE,
    }


# --- Registry ---


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    run: Callable[[Session, Any], dict[str, Any]]


TOOLS: dict[str, Tool] = {
    tool.spec.name: tool
    for tool in [
        Tool(
            ToolSpec(
                "spending_summary",
                "Total spending and receipt count, optionally filtered and grouped. "
                "Use this for any 'how much did I spend' question.",
                SpendingSummaryArgs,
            ),
            spending_summary,
        ),
        Tool(
            ToolSpec(
                "list_receipts",
                "List individual receipts matching filters, e.g. the largest purchases or "
                "receipts that need review.",
                ListReceiptsArgs,
            ),
            list_receipts,
        ),
        Tool(
            ToolSpec(
                "get_receipt",
                "Full details of one receipt: line items, tax, tip, payment method, flags.",
                GetReceiptArgs,
            ),
            get_receipt,
        ),
        Tool(
            ToolSpec(
                "search_line_items",
                "Find purchased items by name (e.g. 'coffee', 'printer ink') and total them.",
                SearchLineItemsArgs,
            ),
            search_line_items,
        ),
    ]
}

TOOL_SPECS = [tool.spec for tool in TOOLS.values()]


def run_tool(db: Session, call: ToolCall) -> dict[str, Any]:
    """Validate the model's arguments and run the tool. Mistakes go back to the model."""
    tool = TOOLS.get(call.name)
    if tool is None:
        return {"error": f"Unknown tool '{call.name}'. Available: {', '.join(TOOLS)}."}
    try:
        args = tool.spec.parameters.model_validate(call.arguments)
    except ValidationError as exc:
        return {"error": f"Invalid arguments for {call.name}: {exc}"}
    return tool.run(db, args)
