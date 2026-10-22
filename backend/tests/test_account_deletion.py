"""Deleting an account removes the user, all their data, and their uploaded files."""

from sqlalchemy import func, select

from app.models import DailyUsage, InboundEmail, LineItem, Receipt, ReceiptFlag, UsageKind, User
from app.quota import try_use_daily
from tests.factories import PASSWORD, add_receipt
from tests.fakes import PNG_BYTES, unique_png


def count(db, model, **where) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return db.scalar(query)


def delete(client, password: str | None = PASSWORD):
    return client.request("DELETE", "/auth/me", json={"password": password})


def test_deletes_the_user_their_data_and_their_files(client, user, db_session, storage):
    uploaded = client.post("/receipts", files={"file": ("r.png", PNG_BYTES)}).json()
    file_key = db_session.get(Receipt, uploaded["id"]).file_key
    add_receipt(db_session, line_items=[("Latte", "4.50")], flags=[("validation", "x")])
    email = InboundEmail(
        message_id="m1",
        user_id=user.id,
        from_email="a@example.com",
        subject="Fwd: order",
        is_receipt=False,
        classification_reason="Not a receipt.",
    )
    db_session.add(email)
    try_use_daily(db_session, user, UsageKind.QUESTIONS)
    db_session.flush()
    user_id = user.id

    response = delete(client)

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(User, user_id) is None
    for model in (Receipt, InboundEmail, DailyUsage):
        assert count(db_session, model, user_id=user_id) == 0
    assert count(db_session, LineItem) == count(db_session, ReceiptFlag) == 0
    assert not (storage.root / file_key).exists()


def test_logs_you_out(client):
    assert delete(client).status_code == 204

    assert client.get("/auth/me").status_code == 401
    assert client.get("/receipts").status_code == 401


def test_needs_the_right_password(client, user, db_session):
    assert delete(client, "wrong password").status_code == 403
    assert delete(client, None).status_code == 403

    db_session.expire_all()
    assert db_session.get(User, user.id) is not None


def test_other_accounts_are_untouched(client, other_client, other_user, db_session, storage):
    theirs = other_client.post("/receipts", files={"file": ("r.png", unique_png(1))}).json()
    their_file = db_session.get(Receipt, theirs["id"]).file_key

    delete(client)

    db_session.expire_all()
    assert db_session.get(User, other_user.id) is not None
    assert db_session.get(Receipt, theirs["id"]) is not None
    assert (storage.root / their_file).exists()


def test_demo_accounts_can_be_deleted_without_a_password(anon_client, db_session):
    anon_client.post("/auth/demo")

    assert delete(anon_client, None).status_code == 204
    assert count(db_session, User, is_demo=True) == 0


def test_requires_login(anon_client):
    assert delete(anon_client).status_code == 401
