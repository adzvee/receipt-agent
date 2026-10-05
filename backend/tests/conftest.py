from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.llm import get_llm
from app.main import app
from app.storage import LocalFileStorage, get_storage
from tests.factories import make_extracted_receipt
from tests.fakes import FakeLLM

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Bring the database schema up to date once per test run."""
    command.upgrade(Config(BACKEND_DIR / "alembic.ini"), "head")


@pytest.fixture
def db_session(migrated_database) -> Iterator[Session]:
    """A session whose changes are rolled back after each test, even if the code commits."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM(response=make_extracted_receipt())


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "storage")


@pytest.fixture
def client(db_session, fake_llm, storage) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_llm] = lambda: fake_llm
    app.dependency_overrides[get_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()
