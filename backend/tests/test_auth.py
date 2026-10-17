from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app import auth
from app.auth import ALGORITHM, COOKIE_NAME, create_access_token, signing_key, verify_password
from app.config import get_settings
from tests.factories import PASSWORD


def register(client, email="new-user@example.com", password="a long enough password"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_register_logs_in_with_an_httponly_cookie(anon_client):
    response = register(anon_client, email="New-User@Example.com")

    assert response.status_code == 201
    assert response.json()["email"] == "new-user@example.com"  # stored lowercase
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert anon_client.get("/auth/me").json()["email"] == "new-user@example.com"


def test_password_is_stored_hashed(anon_client, db_session):
    from app.models import User

    register(anon_client, password="a long enough password")

    user = db_session.query(User).filter_by(email="new-user@example.com").one()
    assert user.password_hash.startswith("$argon2id$")
    assert "a long enough password" not in user.password_hash


def test_duplicate_email_is_rejected(anon_client, user):
    response = register(anon_client, email=user.email.upper())

    assert response.status_code == 409


def test_short_password_and_invalid_email_are_rejected(anon_client):
    assert register(anon_client, password="short").status_code == 422
    assert register(anon_client, email="not-an-email").status_code == 422


def test_login_with_correct_password(anon_client, user):
    response = anon_client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    assert anon_client.get("/auth/me").json()["email"] == user.email


def test_wrong_password_and_unknown_email_get_the_same_error(anon_client, user):
    wrong_password = anon_client.post(
        "/auth/login", json={"email": user.email, "password": "wrong password!"}
    )
    unknown_email = anon_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong password!"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password."}


def test_logout_clears_the_cookie(anon_client, user):
    anon_client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert anon_client.get("/auth/me").status_code == 200

    response = anon_client.post("/auth/logout")

    assert response.status_code == 204
    assert 'session=""' in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert anon_client.get("/auth/me").status_code == 401


def test_protected_routes_require_login(anon_client):
    for method, path in [
        ("GET", "/receipts"),
        ("GET", "/receipts/1"),
        ("POST", "/receipts"),
        ("PATCH", "/receipts/1"),
        ("GET", "/stats/spending"),
        ("POST", "/chat"),
        ("GET", "/auth/me"),
    ]:
        assert anon_client.request(method, path).status_code == 401, (method, path)


def test_bearer_header_works_for_api_clients(anon_client, user):
    token = create_access_token(user.id)

    response = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["email"] == user.email


def test_expired_token_is_rejected(anon_client, user):
    past = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode(
        {"sub": str(user.id), "iat": past, "exp": past + timedelta(hours=1)},
        signing_key(),
        algorithm=ALGORITHM,
    )

    assert (
        anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )


def test_forged_tokens_are_rejected(anon_client, user):
    claims = {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(hours=1)}
    wrong_key = jwt.encode(claims, "x" * 48, algorithm=ALGORITHM)  # a different secret
    unsigned = jwt.encode(claims, None, algorithm="none")  # the "alg: none" trick

    for token in [wrong_key, unsigned, "garbage"]:
        headers = {"Authorization": f"Bearer {token}"}
        assert anon_client.get("/auth/me", headers=headers).status_code == 401


def test_token_for_deleted_user_is_rejected(anon_client, db_session, other_user):
    token = create_access_token(other_user.id)
    db_session.delete(other_user)
    db_session.flush()

    assert (
        anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )


def test_unusable_password_hash_never_matches():
    # The migration's "legacy" owner and demo accounts have the hash "!".
    assert verify_password("anything at all", "!") is False


def test_short_jwt_secret_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "too-short")
    auth.signing_key.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="at least 32 characters"):
            auth.signing_key()
    finally:
        monkeypatch.undo()
        auth.signing_key.cache_clear()


def test_missing_jwt_secret_is_refused_outside_development(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    auth.signing_key.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET must be set"):
            auth.signing_key()
    finally:
        monkeypatch.undo()
        auth.signing_key.cache_clear()
