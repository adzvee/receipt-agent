"""Incoming webhooks from third-party services."""

import logging
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.config import get_settings
from app.db import DbSession
from app.email.inbound import PostmarkInboundEmail, handle_inbound_email
from app.llm import LLMDep, LLMError
from app.storage import StorageDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

basic_auth = HTTPBasic(auto_error=False)


def require_postmark_credentials(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)],
) -> None:
    """Postmark doesn't sign webhooks, so we put a username and password in the webhook URL."""
    settings = get_settings()
    expected_user = settings.postmark_inbound_username
    expected_password = settings.postmark_inbound_password
    if not expected_user or not expected_password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Email forwarding is disabled.")
    # compare_digest takes the same time whether the first or last character is wrong,
    # so an attacker can't guess the password one character at a time.
    valid = (
        credentials is not None
        and secrets.compare_digest(credentials.username.encode(), expected_user.encode())
        and secrets.compare_digest(credentials.password.encode(), expected_password.encode())
    )
    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )


class InboundEmailResponse(BaseModel):
    status: Literal["processed", "duplicate", "ignored"]
    is_receipt: bool
    reason: str
    receipt_ids: list[int]


@router.post(
    "/postmark/inbound",
    response_model=InboundEmailResponse,
    dependencies=[Depends(require_postmark_credentials)],
)
def postmark_inbound(
    email: PostmarkInboundEmail, db: DbSession, storage: StorageDep, llm: LLMDep
) -> InboundEmailResponse:
    """Receive a forwarded email from Postmark.

    Any 200 response tells Postmark we're done with the email, even if it wasn't a
    receipt. Errors make Postmark retry later, which we want only when the failure is
    temporary (e.g. the LLM is unavailable).
    """
    try:
        result = handle_inbound_email(
            db=db,
            storage=storage,
            llm=llm,
            email=email,
            max_attachment_bytes=get_settings().max_upload_bytes,
        )
    except LLMError as exc:
        logger.exception("Couldn't classify email %s; asking Postmark to retry", email.message_id)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Temporarily unable to process email."
        ) from exc

    if result.email is None:
        # Still a 200: an unknown address won't start working if Postmark retries.
        return InboundEmailResponse(
            status=result.status, is_receipt=False, reason="Unknown recipient.", receipt_ids=[]
        )
    return InboundEmailResponse(
        status=result.status,
        is_receipt=result.email.is_receipt,
        reason=result.email.classification_reason,
        receipt_ids=[r.id for r in result.receipts],
    )
