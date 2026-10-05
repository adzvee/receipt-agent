from datetime import date

from app.models import Category
from tests.factories import add_receipt


def test_spending_by_category_in_a_date_range(client, db_session):
    add_receipt(db_session, total="10.00", purchase_date=date(2026, 9, 3))
    add_receipt(
        db_session, total="40.00", purchase_date=date(2026, 9, 20), category=Category.GROCERIES
    )
    add_receipt(db_session, total="99.00", purchase_date=date(2026, 8, 31))  # outside range

    response = client.get(
        "/stats/spending",
        params={"group_by": "category", "start_date": "2026-09-01", "end_date": "2026-09-30"},
    )

    assert response.status_code == 200
    assert [(g["category"], g["total"]) for g in response.json()["groups"]] == [
        ("groceries", "40.00"),
        ("dining", "10.00"),
    ]


def test_category_filter_accepts_repeated_query_params(client, db_session):
    add_receipt(db_session, total="10.00", category=Category.DINING)
    add_receipt(db_session, total="40.00", category=Category.GROCERIES)
    add_receipt(db_session, total="5.00", category=Category.TRANSPORTATION)

    response = client.get(
        "/stats/spending", params=[("categories", "dining"), ("categories", "groceries")]
    )

    assert response.json()["groups"][0]["total"] == "50.00"


def test_invalid_group_by_is_rejected(client):
    assert client.get("/stats/spending", params={"group_by": "weekday"}).status_code == 422
