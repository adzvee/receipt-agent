"""Sign up, log in, log out, and the "Try demo" button."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import delete_account
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
from app.demo import DemoCapacityError, create_demo_account
from app.models import UsageKind, User
from app.quota import left_today
from app.rate_limit import client_ip, demo_per_ip, login_per_email, login_per_ip, register_per_ip
from app.storage import StorageDep

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    # Length matters more than character rules; 128 caps the cost of hashing.
    password: str = Field(min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    # Required for regular accounts, so a session left open on a shared computer can't
    # be used to wipe the account. Demo accounts have no password.
    password: str | None = Field(None, max_length=128)


class UserOut(BaseModel):
    email: str
    is_demo: bool
    # Where to forward receipt emails, if email forwarding is set up (not for demos).
    forwarding_address: str | None
    demo_requests_left: int | None
    receipts_left_today: int
    questions_left_today: int


def user_out(user: User, db: Session) -> UserOut:
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
        receipts_left_today=left_today(db, user, UsageKind.RECEIPTS),
        questions_left_today=left_today(db, user, UsageKind.QUESTIONS),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    credentials: Credentials, request: Request, response: Response, db: DbSession
) -> UserOut:
    register_per_ip.check(client_ip(request), "Too many sign-ups. Please try again later.")
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
    return user_out(user, db)


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response, db: DbSession) -> UserOut:
    message = "Too many login attempts. Please wait a minute and try again."
    login_per_ip.check(client_ip(request), message)
    login_per_email.check(credentials.email.lower(), message)
    user = db.scalars(select(User).where(User.email == credentials.email.lower())).first()
    # A password is checked (against a dummy hash if the email is unknown) and the message
    # is the same either way, so neither the reply nor its timing reveals who has an account.
    password_ok = verify_password(credentials.password, user.password_hash if user else None)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    set_session_cookie(response, user.id)
    return user_out(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: DeleteAccountRequest,
    user: CurrentUser,
    response: Response,
    db: DbSession,
    storage: StorageDep,
) -> None:
    """Permanently delete the account, all its receipts, and their files."""
    if not user.is_demo and not verify_password(body.password or "", user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That password isn't right.")
    delete_account(db, storage, user)
    db.commit()
    clear_session_cookie(response)


@router.get("/me")
def me(user: CurrentUser, db: DbSession) -> UserOut:
    return user_out(user, db)


@router.post("/demo", status_code=status.HTTP_201_CREATED)
def try_demo(request: Request, response: Response, db: DbSession, storage: StorageDep) -> UserOut:
    """Create a private demo account with two months of fake receipts, and log into it."""
    demo_per_ip.check(client_ip(request), "Too many demos started. Please try again later.")
    try:
        user = create_demo_account(db, storage)
    except DemoCapacityError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The demo is busy right now. Please try again later, or create an account.",
        ) from None
    set_session_cookie(response, user.id)
    return user_out(user, db)
