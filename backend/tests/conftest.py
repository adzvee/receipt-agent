from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, create_access_token
from app.categorization import CategoryDecision
from app.config import get_settings
from app.db import get_db
from app.email.inbound import EmailClassification
from app.extraction import ExtractedReceipt
from app.llm import get_llm
from app.main import app
from app.models import User
from app.storage import LocalFileStorage, get_storage
from tests.factories import default_user, make_category_decision, make_extracted_receipt, make_user
from tests.fakes import FakeLLM

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> URL:
    """Same server as the app's database, but a separate `<name>_test` database.

    Keeping tests out of the development database means your own receipts can't change
    test results (e.g. by adding spending history to the anomaly checks).
    """
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test")


def _create_database_if_missing(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Create the test database if needed and bring its schema up to date, once per run."""
    url = _test_database_url()
    _create_database_if_missing(url)

    alembic_config = Config(BACKEND_DIR / "alembic.ini")
    alembic_config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(alembic_config, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Iterator[Session]:
    """A session whose changes are rolled back after each test, even if the code commits."""
    connection = test_engine.connect()
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
    return FakeLLM(
        responses={
            ExtractedReceipt: make_extracted_receipt(),
            CategoryDecision: make_category_decision(),
            EmailClassification: EmailClassification(
                is_receipt=True, receipt_location="attachments", reason="It's a receipt."
            ),
        }
    )


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "storage")


@pytest.fixture
def user(db_session) -> User:
    return default_user(db_session)


@pytest.fixture
def other_user(db_session) -> User:
    return make_user(db_session, "someone-else@example.com")


@pytest.fixture
def anon_client(db_session, fake_llm, storage) -> Iterator[TestClient]:
    """A client that isn't logged in."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_llm] = lambda: fake_llm
    app.dependency_overrides[get_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()


def logged_in_client(user: User) -> TestClient:
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, create_access_token(user.id))
    return client


@pytest.fixture
def client(anon_client, user) -> TestClient:
    """A client logged in as the default test user."""
    return logged_in_client(user)


@pytest.fixture
def other_client(anon_client, other_user) -> TestClient:
    """A client logged in as a different user, for checking data isolation."""
    return logged_in_client(other_user)
