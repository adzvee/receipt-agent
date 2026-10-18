from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError

from app.agent.tools import run_tool
from app.db import make_read_only
from app.llm import ToolCall
from app.models import Category, FlagKind, ReceiptStatus
from tests.factories import add_receipt, default_user


def call(db, name: str, **arguments) -> dict:
    return run_tool(db, ToolCall(id=None, name=name, arguments=arguments), default_user(db).id)


@pytest.fixture
def september(db_session):
    """A small month of fake spending."""
    add_receipt(db_session, vendor="Corner Cafe", total="8.00", purchase_date=date(2026, 9, 2))
    add_receipt(db_session, vendor="CORNER CAFE #2", total="12.00", purchase_date=date(2026, 9, 9))
    add_receipt(
        db_session,
        vendor="Fresh Mart",
        total="60.00",
        purchase_date=date(2026, 9, 30),
        category=Category.GROCERIES,
        line_items=[("Organic coffee beans", "14.00"), ("Milk", "4.00")],
    )
    add_receipt(
        db_session,
        vendor="City Transit",
        total="25.00",
        purchase_date=date(2026, 10, 1),  # just outside September
        category=Category.TRANSPORTATION,
    )


# --- spending_summary ---


def test_spending_in_a_date_range_and_categories(db_session, september):
    result = call(
        db_session,
        "spending_summary",
        start_date="2026-09-01",
        end_date="2026-09-30",
        categories=["groceries", "dining"],
    )

    assert result["groups"] == [{"currency": "USD", "total": "80.00", "receipt_count": 3}]


def test_spending_grouped_by_category(db_session, september):
    result = call(db_session, "spending_summary", group_by="category")

    assert [(g["category"], g["total"]) for g in result["groups"]] == [
        ("groceries", "60.00"),
        ("transportation", "25.00"),
        ("dining", "20.00"),
    ]


def test_spending_grouped_by_vendor_merges_name_variants(db_session, september):
    result = call(db_session, "spending_summary", group_by="vendor", categories=["dining"])

    [group] = result["groups"]
    assert group["total"] == "20.00"
    assert group["receipt_count"] == 2


def test_spending_grouped_by_month(db_session, september):
    result = call(db_session, "spending_summary", group_by="month")

    assert [(g["month"], g["total"]) for g in result["groups"]] == [
        ("2026-09", "80.00"),
        ("2026-10", "25.00"),
    ]


def test_spending_excludes_open_duplicates_and_failed_receipts(db_session):
    add_receipt(db_session, total="10.00")
    add_receipt(db_session, total="10.00", flags=[(FlagKind.DUPLICATE, "likely_duplicate")])
    add_receipt(db_session, total="99.00", status=ReceiptStatus.FAILED)

    result = call(db_session, "spending_summary")

    assert result["groups"] == [{"currency": "USD", "total": "10.00", "receipt_count": 1}]


def test_dismissed_duplicate_counts_again(db_session):
    receipt = add_receipt(
        db_session, total="10.00", flags=[(FlagKind.DUPLICATE, "likely_duplicate")]
    )
    receipt.flags[0].dismissed_at = datetime.now(UTC)
    db_session.flush()

    assert call(db_session, "spending_summary")["groups"][0]["total"] == "10.00"


def test_currencies_are_never_added_together(db_session):
    add_receipt(db_session, total="10.00", currency="USD")
    add_receipt(db_session, total="20.00", currency="EUR")

    result = call(db_session, "spending_summary")

    assert {(g["currency"], g["total"]) for g in result["groups"]} == {
        ("USD", "10.00"),
        ("EUR", "20.00"),
    }


def test_no_matching_spending_says_the_empty_result_is_final(db_session, september):
    result = call(db_session, "spending_summary", start_date="2020-01-01", end_date="2020-12-31")

    assert result["groups"] == []
    assert "complete answer" in result["result"]
    assert "no receipts yet" not in result["result"]  # the account does have receipts


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("spending_summary", {"categories": ["groceries", "dining"], "group_by": "category"}),
        ("list_receipts", {"sort": "largest"}),
        ("search_line_items", {"text": "coffee"}),
    ],
)
def test_empty_account_says_there_are_no_receipts_yet(db_session, name, arguments):
    default_user(db_session)  # exists, with no receipts

    result = call(db_session, name, **arguments)

    assert "error" not in result  # categories with no receipts are still valid filters
    assert "no receipts yet" in result["result"]


# --- list_receipts / get_receipt ---


def test_list_largest_receipts_with_limit(db_session, september):
    result = call(db_session, "list_receipts", sort="largest", limit=2)

    assert [r["vendor"] for r in result["receipts"]] == ["Fresh Mart", "City Transit"]
    assert result["more_results"] is True


def test_list_receipts_needing_review(db_session):
    add_receipt(db_session, vendor="Clean Cafe")
    add_receipt(db_session, vendor="Odd Cafe", flags=[(FlagKind.ANOMALY, "high_tip")])

    result = call(db_session, "list_receipts", needs_review=True)

    assert [r["vendor"] for r in result["receipts"]] == ["Odd Cafe"]
    assert result["receipts"][0]["open_flags"] == ["high_tip"]


def test_get_receipt_details(db_session, september):
    receipt_id = call(db_session, "list_receipts", vendor="fresh")["receipts"][0]["id"]

    result = call(db_session, "get_receipt", receipt_id=receipt_id)

    assert result["vendor"] == "Fresh Mart"
    assert [i["description"] for i in result["line_items"]] == ["Organic coffee beans", "Milk"]


def test_get_missing_receipt_returns_error(db_session):
    assert call(db_session, "get_receipt", receipt_id=999999) == {
        "error": "There is no receipt #999999."
    }


# --- search_line_items ---


def test_search_line_items_is_case_insensitive_and_totals(db_session, september):
    result = call(db_session, "search_line_items", text="COFFEE")

    assert [m["description"] for m in result["matches"]] == ["Organic coffee beans"]
    assert result["totals"] == [{"currency": "USD", "total": "14.00", "item_count": 1}]


def test_search_treats_wildcards_literally(db_session):
    add_receipt(db_session, line_items=[("Milk", "4.00")])

    # In SQL LIKE, "%" would match everything; here it must match only a literal "%".
    assert call(db_session, "search_line_items", text="%")["matches"] == []


# --- Guard rails ---


def test_unknown_tool_returns_error_to_model(db_session):
    result = call(db_session, "delete_everything")

    assert result["error"].startswith("Unknown tool 'delete_everything'")


def test_invalid_arguments_return_error_to_model(db_session):
    result = call(db_session, "spending_summary", categories=["snacks"])

    assert "Invalid arguments for spending_summary" in result["error"]


def test_read_only_transaction_rejects_writes(db_session):
    make_read_only(db_session)

    with pytest.raises(InternalError, match="read-only transaction"):
        db_session.execute(text("DELETE FROM receipts"))
    db_session.rollback()
