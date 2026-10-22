"""Deleting an account and everything in it."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Receipt, User
from app.storage import FileStorage

logger = logging.getLogger(__name__)


def delete_account(db: Session, storage: FileStorage, user: User) -> None:
    """Delete the user, their data, and their uploaded files. The caller commits.

    The database removes the rest with the user (ON DELETE CASCADE): receipts with their
    line items and flags, forwarded emails, and usage counts.
    """
    file_keys = list(db.scalars(select(Receipt.file_key).where(Receipt.user_id == user.id)))
    db.delete(user)
    db.flush()  # delete the rows first: if that fails, no files are lost
    for key in file_keys:
        try:
            storage.delete(key)
        except OSError:
            logger.exception("Couldn't delete file %s of a deleted account", key)
