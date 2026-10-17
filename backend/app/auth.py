"""Passwords, login tokens, and finding the current user.

- Passwords are hashed with Argon2 (via pwdlib); only the hash is stored.
- A login token is a JWT signed with JWT_SECRET, holding the user id and an expiry.
- The browser keeps the token in an HttpOnly cookie, which page JavaScript can't read,
  so a script-injection bug couldn't steal it. API clients may send it as a Bearer header.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import Settings, get_settings
from app.db import DbSession
from app.models import User

logger = logging.getLogger(__name__)

COOKIE_NAME = "session"
ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32  # a short HMAC secret can be brute-forced from a single token

_password_hash = PasswordHash.recommended()
# Checked against when the email doesn't exist, so a login attempt takes the same time
# either way and can't reveal which emails have accounts.
_DUMMY_HASH = _password_hash.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _password_hash.verify(password, password_hash or _DUMMY_HASH)
    except UnknownHashError:  # e.g. the legacy account's unusable "!" hash
        return False


def new_inbound_token() -> str:
    return secrets.token_hex(8)


@lru_cache
def signing_key() -> str:
    settings = get_settings()
    if settings.jwt_secret:
        if len(settings.jwt_secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters.")
        return settings.jwt_secret
    if settings.app_env != "development":
        raise RuntimeError("JWT_SECRET must be set when APP_ENV isn't 'development'.")
    logger.warning("JWT_SECRET is not set; using a random key (logins reset on restart).")
    return secrets.token_urlsafe(48)


def create_access_token(user_id: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, signing_key(), algorithm=ALGORITHM)


def user_id_from_token(token: str) -> int | None:
    """The user id in a valid, unexpired token we signed; None for anything else."""
    try:
        # Passing `algorithms` explicitly rejects tokens claiming another algorithm
        # (including the classic "alg: none" forgery).
        claims = jwt.decode(token, signing_key(), algorithms=[ALGORITHM])
        return int(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def set_session_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,  # not readable from JavaScript
        samesite="lax",  # not sent on requests started by other sites (CSRF protection)
        secure=settings.app_env != "development",  # HTTPS-only outside local development
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")


def get_current_user(request: Request, db: DbSession) -> User:
    """FastAPI dependency: the logged-in user, or a 401."""
    token = request.cookies.get(COOKIE_NAME)
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ")

    user_id = user_id_from_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
