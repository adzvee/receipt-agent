"""Database engine, session factory, and the declarative base all models inherit from."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
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


# Type alias for route parameters: `def route(db: DbSession): ...`
DbSession = Annotated[Session, Depends(get_db)]
