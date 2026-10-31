import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings
from app.main import app


# ---------- DATABASE_URL normalisation ----------

@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgres://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),  # already right
        ("sqlite://", "sqlite://"),  # untouched
    ],
)
def test_database_url_gets_the_driver_name(given, expected):
    assert Settings(database_url=given).database_url == expected


def test_neon_style_url_with_ssl_options_parses():
    url = "postgresql://user:pw@ep-cool-123.ap-south-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    parsed = make_url(Settings(database_url=url).database_url)
    assert parsed.drivername == "postgresql+psycopg2"
    assert parsed.host == "ep-cool-123.ap-south-1.aws.neon.tech"
    assert parsed.query["sslmode"] == "require"


# ---------- production safety check ----------

def test_production_rejects_the_default_secret():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="change-me").assert_production_ready()


def test_production_rejects_a_short_secret():
    with pytest.raises(RuntimeError):
        Settings(environment="production", secret_key="short").assert_production_ready()


def test_production_accepts_a_long_random_secret():
    Settings(environment="production", secret_key="x" * 40).assert_production_ready()


def test_development_does_not_check_the_secret():
    Settings(environment="development", secret_key="change-me").assert_production_ready()


def test_app_refuses_to_start_in_production_with_a_weak_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "change-me")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_app_starts_in_production_with_a_strong_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "y" * 48)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
