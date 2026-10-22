"""Per-account daily limits on receipts and chat questions."""

from datetime import date, timedelta

from app.config import get_settings
from app.llm import AssistantMessage
from app.models import UsageKind
from app.quota import left_today, try_use_daily
from tests.fakes import unique_png
from tests.test_email_inbound import attachment, classify_as, make_email, post


def upload(client, n: int):
    return client.post("/receipts", files={"file": ("r.png", unique_png(n))})


def test_sixth_upload_of_the_day_is_refused(client):
    statuses = [upload(client, n).status_code for n in range(6)]

    assert statuses == [201] * 5 + [429]
    refused = upload(client, 99).json()["detail"]
    assert "today's limit of 5 receipts" in refused and "midnight UTC" in refused


def test_eleventh_question_of_the_day_is_refused(client, fake_llm):
    fake_llm.chat_replies = [AssistantMessage(text="$0.")] * 10

    statuses = [client.post("/chat", json={"question": "Hi"}).status_code for _ in range(11)]

    assert statuses == [200] * 10 + [429]
    assert len(fake_llm.chat_calls) == 10  # the model wasn't asked the 11th


def test_limits_are_per_account(client, other_client):
    for n in range(5):
        upload(client, n)

    assert upload(other_client, 100).status_code == 201


def test_yesterdays_use_does_not_count_today(db_session, user):
    yesterday = date.today() - timedelta(days=1)
    for _ in range(5):
        try_use_daily(db_session, user, UsageKind.RECEIPTS, today=yesterday)

    assert not try_use_daily(db_session, user, UsageKind.RECEIPTS, today=yesterday)
    assert left_today(db_session, user, UsageKind.RECEIPTS) == 5


def test_me_shows_what_is_left_today(client):
    upload(client, 1)

    me = client.get("/auth/me").json()

    assert me["receipts_left_today"] == 4
    assert me["questions_left_today"] == 10


def test_forwarded_receipts_count_toward_the_same_limit(client, fake_llm, monkeypatch):
    monkeypatch.setattr(get_settings(), "postmark_inbound_username", "postmark")
    monkeypatch.setattr(get_settings(), "postmark_inbound_password", "test-password")
    for n in range(4):
        upload(client, n)
    classify_as(fake_llm, is_receipt=True, location="attachments")
    email = make_email(
        Attachments=[attachment("a.png", unique_png(10)), attachment("b.png", unique_png(11))]
    )

    response = post(client, email, auth=("postmark", "test-password")).json()

    assert len(response["receipt_ids"]) == 1  # one left today: the second is skipped

    # Once at the limit, emails are ignored before the model is even asked.
    calls_before = len(fake_llm.calls)
    later = post(client, make_email(MessageID="msg-2"), auth=("postmark", "test-password"))
    assert later.json()["status"] == "ignored"
    assert len(fake_llm.calls) == calls_before
