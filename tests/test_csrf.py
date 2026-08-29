"""Confirm CSRFProtect is actually wired up app-wide.

The rest of the suite disables WTF_CSRF_ENABLED for convenience, which
would silently hide a regression where CSRF protection gets dropped (e.g.
from app/__init__.py). This module builds its own app with CSRF left on.
"""

import re

import pytest

from app import create_app
from app import db as _db
from app.models import User


@pytest.fixture()
def csrf_app(tmp_path):
    db_path = tmp_path / "csrf-test.db"
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SECRET_KEY": "test-secret",
        }
    )
    with application.app_context():
        _db.create_all()
        user = User(email="admin@example.com", name="Admin", is_admin=True)
        user.set_password("adminpass123")
        _db.session.add(user)
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_login_post_without_csrf_token_is_rejected(csrf_client):
    response = csrf_client.post(
        "/login",
        data={"email": "admin@example.com", "password": "adminpass123"},
    )
    assert response.status_code == 400


def test_login_post_with_csrf_token_succeeds(csrf_client):
    get_response = csrf_client.get("/login")
    match = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"', get_response.text
    )
    assert match, "login form should render a CSRF token"

    response = csrf_client.post(
        "/login",
        data={
            "email": "admin@example.com",
            "password": "adminpass123",
            "csrf_token": match.group(1),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.request.path == "/concerts"
