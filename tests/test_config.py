"""App factory configuration."""

import pytest

from app import create_app, normalize_database_url


def test_create_app_refuses_to_start_without_a_database_url(monkeypatch):
    """No SQLite fallback: an unset DATABASE_URL has to fail loudly rather
    than quietly pointing a command at a stray local file."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app()


def test_create_app_accepts_an_explicit_uri_without_the_env_var(monkeypatch):
    """How the tests and scripts/sqlite_to_pg.py build an app."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app({"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://x/y"})

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg://x/y"


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"],
)
def test_bare_postgres_urls_are_pointed_at_psycopg(given):
    """DigitalOcean hands out the bare form; SQLAlchemy would read it as
    psycopg2, which isn't installed."""
    assert normalize_database_url(given) == "postgresql+psycopg://u:p@h:5432/d"


def test_other_urls_are_left_alone():
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
    explicit = "postgresql+psycopg://u@h/d"
    assert normalize_database_url(explicit) == explicit
