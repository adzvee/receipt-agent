"""Sign up, log in, log out, and the "Try demo" button."""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import (
    CurrentUser,
    clear_session_cookie,
    hash_password,
    new_inbound_token,
    set_session_cookie,
    verify_password,
)
from app.config import get_settings
from app.db import DbSession
from app.demo import create_demo_account
from app.models import User
from app.storage import StorageDep

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    # Length matters more than character rules; 128 caps the cost of hashing.
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    email: str
    is_demo: bool
    # Where to forward receipt emails, if email forwarding is set up (not for demos).
    forwarding_address: str | None
    demo_requests_left: int | None


def user_out(user: User) -> UserOut:
    settings = get_settings()
    forwarding = None
    if settings.postmark_inbound_address and not user.is_demo:
        inbox, domain = settings.postmark_inbound_address.split("@", 1)
        forwarding = f"{inbox}+{user.inbound_token}@{domain}"
    left = (
        max(settings.demo_llm_request_limit - user.llm_requests_used, 0) if user.is_demo else None
    )
    return UserOut(
        email=user.email,
        is_demo=user.is_demo,
        forwarding_address=forwarding,
        demo_requests_left=left,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(credentials: Credentials, response: Response, db: DbSession) -> UserOut:
    user = User(
        email=credentials.email.lower(),
        password_hash=hash_password(credentials.password),
        inbound_token=new_inbound_token(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists."
        ) from None
    set_session_cookie(response, user.id)
    return user_out(user)


@router.post("/login")
def login(credentials: Credentials, response: Response, db: DbSession) -> UserOut:
    user = db.scalars(select(User).where(User.email == credentials.email.lower())).first()
    # A password is checked (against a dummy hash if the email is unknown) and the message
    # is the same either way, so neither the reply nor its timing reveals who has an account.
    password_ok = verify_password(credentials.password, user.password_hash if user else None)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    set_session_cookie(response, user.id)
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.post("/demo", status_code=status.HTTP_201_CREATED)
def try_demo(response: Response, db: DbSession, storage: StorageDep) -> UserOut:
    """Create a private demo account with two months of fake receipts, and log into it."""
    user = create_demo_account(db, storage)
    set_session_cookie(response, user.id)
    return user_out(user)
