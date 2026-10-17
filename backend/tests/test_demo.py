from collections import Counter
from datetime import UTC, date, datetime, timedelta

from app.config import get_settings
from app.demo import DEMO_DAYS, create_demo_account, delete_expired_demo_accounts
from app.models import Receipt, User
from tests.fakes import PNG_BYTES

TODAY = date(2026, 10, 17)


def test_try_demo_logs_into_a_new_private_account(anon_client):
    response = anon_client.post("/auth/demo")

    assert response.status_code == 201
    body = response.json()
    assert body["is_demo"] is True
    assert body["email"].endswith("@demo.invalid")
    assert body["forwarding_address"] is None
    assert body["demo_requests_left"] == get_settings().demo_llm_request_limit
    assert anon_client.get("/auth/me").json()["email"] == body["email"]


def test_each_visitor_gets_their_own_demo(anon_client, other_client):
    first = anon_client.post("/auth/demo").json()["email"]
    second = other_client.post("/auth/demo").json()["email"]

    assert first != second


def test_demo_has_two_months_of_receipts_with_every_kind_of_flag(db_session, storage):
    user = create_demo_account(db_session, storage, today=TODAY)

    receipts = db_session.query(Receipt).filter_by(user_id=user.id).all()
    dates = [r.purchase_date for r in receipts]
    assert len(receipts) >= 50
    assert min(dates) >= TODAY - timedelta(days=DEMO_DAYS)
    assert max(dates) <= TODAY
    assert len({r.category for r in receipts}) >= 8

    open_flags = Counter(f.code for r in receipts for f in r.flags if f.dismissed_at is None)
    assert open_flags["total_mismatch"] == 1
    assert open_flags["likely_duplicate"] == 1
    assert open_flags["high_for_category"] >= 1
    assert open_flags["high_tip"] == 1
    # Only the four deliberately unusual receipts get flagged, never everyday purchases.
    assert sum(1 for r in receipts if r.needs_review) == 4


def test_demo_receipts_have_viewable_files(client, db_session, storage):
    response = client.post("/auth/demo")
    receipt_id = client.get("/receipts").json()[0]["id"]

    file = client.get(f"/receipts/{receipt_id}/file")

    assert response.status_code == 201
    assert file.status_code == 200
    assert "Demo receipt: all details are fake" in file.text


def test_expired_demo_accounts_and_their_files_are_deleted(db_session, storage, user):
    demo = create_demo_account(db_session, storage, today=TODAY)
    keys = [r.file_key for r in db_session.query(Receipt).filter_by(user_id=demo.id)]
    demo.created_at = datetime.now(UTC) - timedelta(hours=get_settings().demo_ttl_hours + 1)
    db_session.flush()

    deleted = delete_expired_demo_accounts(db_session, storage, datetime.now(UTC))
    db_session.flush()

    assert deleted == 1
    assert db_session.get(User, demo.id) is None
    assert db_session.query(Receipt).filter_by(user_id=demo.id).count() == 0
    assert not any((storage.root / key).exists() for key in keys)
    assert db_session.get(User, user.id) is not None  # regular accounts are untouched


def test_demo_cannot_log_in_with_a_password(anon_client):
    email = anon_client.post("/auth/demo").json()["email"]
    anon_client.post("/auth/logout")

    response = anon_client.post("/auth/login", json={"email": email, "password": "!" * 8})

    # Rejected either as an invalid email (".invalid" is reserved) or a wrong password.
    assert response.status_code in {401, 422}
    assert anon_client.get("/auth/me").status_code == 401


def test_demo_ai_requests_are_capped(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_llm_request_limit", 2)
    anon_client.post("/auth/demo")

    for _ in range(2):
        upload = anon_client.post("/receipts", files={"file": ("r.png", PNG_BYTES)})
        assert upload.status_code == 201
    over = anon_client.post("/receipts", files={"file": ("r.png", PNG_BYTES)})
    chat = anon_client.post("/chat", json={"question": "Hi"})

    assert over.status_code == chat.status_code == 429
    assert "Create a free account" in over.json()["detail"]
    assert anon_client.get("/auth/me").json()["demo_requests_left"] == 0


def test_regular_accounts_are_not_capped(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_llm_request_limit", 0)

    assert client.post("/receipts", files={"file": ("r.png", PNG_BYTES)}).status_code == 201
