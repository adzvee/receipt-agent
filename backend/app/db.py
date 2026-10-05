"""Database engine, session factory, and the declarative base all models inherit from."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_read_only(db: Session) -> None:
    """Make the rest of this session's transaction read-only, enforced by Postgres itself.

    A safety net under the agent's tools: even if a tool had a bug that tried to write,
    the database would refuse. Long-running queries are also cut off.
    """
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '5s'"))


# Type alias for route parameters: `def route(db: DbSession): ...`
DbSession = Annotated[Session, Depends(get_db)]
