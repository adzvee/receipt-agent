"""Each user can only ever see and change their own receipts.

`client` is logged in as `user`; `other_client` as `other_user`.
"""

from datetime import date

from app.categorization import CategoryDecision
from app.extraction import ExtractedReceipt
from app.llm import AssistantMessage, ToolCall
from app.models import Category, CategorySource, FlagKind
from tests.factories import add_receipt, make_extracted_receipt
from tests.fakes import PNG_BYTES


def test_receipts_list_shows_only_your_own(client, other_client, user, other_user, db_session):
    mine = add_receipt(db_session, user=user, vendor="My Cafe")
    add_receipt(db_session, user=other_user, vendor="Their Cafe")

    assert [r["id"] for r in client.get("/receipts").json()] == [mine.id]


def test_someone_elses_receipt_looks_like_it_does_not_exist(
    client, other_user, db_session, storage
):
    theirs = add_receipt(db_session, user=other_user, flags=[(FlagKind.ANOMALY, "high_tip")])
    storage.save(theirs.file_key, b"their file", "image/png")
    flag_id = theirs.flags[0].id

    for response in [
        client.get(f"/receipts/{theirs.id}"),
        client.get(f"/receipts/{theirs.id}/file"),
        client.get(f"/receipts/{theirs.id}/thumbnail"),
        client.patch(f"/receipts/{theirs.id}", json={"category": "office"}),
        client.post(f"/receipts/{theirs.id}/flags/{flag_id}/dismiss"),
    ]:
        assert response.status_code == 404
        assert response.json() == {"detail": "Receipt not found."}

    db_session.refresh(theirs)
    assert theirs.category == Category.DINING  # unchanged
    assert theirs.flags[0].dismissed_at is None


def test_stats_include_only_your_spending(client, user, other_user, db_session):
    add_receipt(db_session, user=user, total="10.00")
    add_receipt(db_session, user=other_user, total="999.00")

    groups = client.get("/stats/spending").json()["groups"]

    assert groups == [{"currency": "USD", "total": "10.00", "receipt_count": 1}]


def test_agent_tools_only_see_your_receipts(client, fake_llm, user, other_user, db_session):
    add_receipt(db_session, user=user, total="10.00")
    theirs = add_receipt(db_session, user=other_user, total="999.00", line_items=[("Gold", "999")])
    fake_llm.chat_replies = [
        AssistantMessage(
            tool_calls=[
                ToolCall(id="1", name="spending_summary", arguments={}),
                ToolCall(id="2", name="list_receipts", arguments={}),
                ToolCall(id="3", name="get_receipt", arguments={"receipt_id": theirs.id}),
                ToolCall(id="4", name="search_line_items", arguments={"text": "gold"}),
            ]
        ),
        AssistantMessage(text="Done."),
    ]

    client.post("/chat", json={"question": "Show me everything"})

    results = [m.result for m in fake_llm.chat_calls[1]["messages"][-4:]]
    summary, listed, fetched, searched = results
    assert summary["groups"][0]["total"] == "10.00"
    assert [r["total"] for r in listed["receipts"]] == ["10.00"]
    assert fetched == {"error": f"There is no receipt #{theirs.id}."}
    assert searched["matches"] == []


def test_duplicate_check_ignores_other_users(client, other_user, db_session, fake_llm):
    # The same purchase in someone else's account must not be flagged (or revealed).
    add_receipt(
        db_session,
        user=other_user,
        vendor="Corner Cafe",
        total="8.37",
        purchase_date=date(2026, 9, 14),
    )

    body = client.post("/receipts", files={"file": ("r.png", PNG_BYTES)}).json()

    assert body["flags"] == []


def test_category_history_ignores_other_users(client, other_user, db_session, fake_llm):
    # Someone else's correction for this vendor must not change your category.
    add_receipt(
        db_session, user=other_user, category=Category.OFFICE, category_source=CategorySource.USER
    )

    body = client.post("/receipts", files={"file": ("r.png", PNG_BYTES)}).json()

    assert body["category"] == "dining"
    assert body["category_source"] == "llm"
    assert len(fake_llm.calls_for(CategoryDecision)) == 1


def test_anomaly_history_ignores_other_users(client, other_user, db_session, fake_llm):
    for total in ["9.00", "11.00", "10.00", "12.00", "8.00"] * 2:
        add_receipt(db_session, user=other_user, vendor="Elsewhere", total=total)
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(
        line_items=[], subtotal=None, tax=None, total=95.00
    )

    body = client.post("/receipts", files={"file": ("r.png", PNG_BYTES)}).json()

    assert body["flags"] == []  # you have no dining history of your own yet
