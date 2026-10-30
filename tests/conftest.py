import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables)
from app.core.database import Base, get_db
from app.main import app

# By default tests use a throwaway SQLite database (no setup needed).
# To run the same tests against real PostgreSQL, set TEST_DATABASE_URL to an
# EMPTY test database (its tables are dropped and recreated for every test):
#   TEST_DATABASE_URL=postgresql+psycopg2://clinic:clinic@localhost:5432/clinicslot_test
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture()
def engine():
    if TEST_DATABASE_URL:
        eng = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    if TEST_DATABASE_URL:
        Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def concurrent_engine(tmp_path):
    """An engine where several threads can each hold their OWN connection."""
    if TEST_DATABASE_URL:
        eng = create_engine(TEST_DATABASE_URL, pool_size=20)
        Base.metadata.drop_all(eng)
    else:
        # file-based SQLite so threads don't share one connection; timeout = wait for the write lock
        eng = create_engine(
            f"sqlite:///{tmp_path / 'concurrency.db'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    Base.metadata.create_all(eng)
    yield eng
    if TEST_DATABASE_URL:
        Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
