import pytest

from app.models import User
from app.tokens import make_reset_token, verify_reset_token
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

NEW_PASSWORD = "brandNewPass789"


@pytest.fixture()
def outbox(app):
    return app.extensions.setdefault("mail_outbox", [])


@pytest.fixture()
def flagged_ringer(db, ringer):
    ringer.must_change_password = True
    db.session.commit()
    return ringer


def change_password(client, current, new, confirm=None):
    return client.post(
        "/change-password",
        data={
            "current_password": current,
            "new_password": new,
            "confirm": new if confirm is None else confirm,
        },
        follow_redirects=True,
    )


# --- admin sets the flag ---


def test_admin_created_user_must_change_password(client, db, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        "/admin/user/new/",
        data={"email": "New@Example.com", "name": "New", "password": "temp1234"},
    )
    user = User.query.filter_by(email="new@example.com").one()
    assert user.must_change_password is True


def test_admin_editing_password_sets_flag(client, db, admin_user, ringer):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        f"/admin/user/edit/?id={ringer.id}",
        data={"email": ringer.email, "name": ringer.name, "password": "temp1234"},
    )
    db.session.refresh(ringer)
    assert ringer.must_change_password is True


def test_admin_editing_without_password_leaves_flag(client, db, admin_user, ringer):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        f"/admin/user/edit/?id={ringer.id}",
        data={"email": ringer.email, "name": "Renamed", "password": ""},
    )
    db.session.refresh(ringer)
    assert ringer.name == "Renamed"
    assert ringer.must_change_password is False


def test_admin_setting_own_password_does_not_set_flag(client, db, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        f"/admin/user/edit/?id={admin_user.id}",
        data={
            "email": admin_user.email,
            "name": admin_user.name,
            "is_admin": "y",
            "password": NEW_PASSWORD,
        },
    )
    db.session.refresh(admin_user)
    assert admin_user.check_password(NEW_PASSWORD)
    assert admin_user.must_change_password is False


# --- forced change ---


def test_flagged_user_lands_on_change_password(client, flagged_ringer):
    response = login(client, flagged_ringer, RINGER_PASSWORD)
    assert response.request.path == "/change-password"
    assert b"Please choose a new password" in response.data


def test_flagged_user_cannot_reach_other_pages(client, flagged_ringer):
    login(client, flagged_ringer, RINGER_PASSWORD)
    response = client.get("/concerts")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/change-password")


def test_flagged_user_can_log_out(client, flagged_ringer):
    login(client, flagged_ringer, RINGER_PASSWORD)
    response = client.post("/logout")
    assert response.headers["Location"].endswith("/login")


def test_unflagged_user_is_not_redirected(client, ringer):
    response = login(client, ringer, RINGER_PASSWORD)
    assert response.request.path == "/concerts"


# --- change password ---


def test_change_password_success_clears_flag(client, db, flagged_ringer):
    login(client, flagged_ringer, RINGER_PASSWORD)
    response = change_password(client, RINGER_PASSWORD, NEW_PASSWORD)
    assert response.request.path == "/concerts"
    db.session.refresh(flagged_ringer)
    assert flagged_ringer.must_change_password is False
    client.post("/logout")
    assert login(client, flagged_ringer, NEW_PASSWORD).request.path == "/concerts"


def test_change_password_wrong_current(client, db, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = change_password(client, "wrong-password", NEW_PASSWORD)
    assert b"Current password is incorrect" in response.data
    db.session.refresh(ringer)
    assert ringer.check_password(RINGER_PASSWORD)


def test_change_password_mismatch(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = change_password(client, RINGER_PASSWORD, NEW_PASSWORD, "different99")
    assert b"Passwords must match" in response.data


def test_change_password_too_short(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = change_password(client, RINGER_PASSWORD, "short")
    assert b"at least 8 characters" in response.data


def test_change_password_must_differ(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = change_password(client, RINGER_PASSWORD, RINGER_PASSWORD)
    assert b"must be different" in response.data


def test_change_password_requires_login(client):
    response = client.get("/change-password")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- forgot / reset ---


def test_login_page_links_to_forgot_password(client):
    assert b'href="/forgot-password"' in client.get("/login").data


def test_forgot_password_sends_reset_link(client, outbox, ringer):
    response = client.post(
        "/forgot-password", data={"email": "Ringer@Example.com"}, follow_redirects=True
    )
    assert b"a reset link is on its way" in response.data
    assert len(outbox) == 1
    assert outbox[0]["To"] == ringer.email
    assert "http://localhost/reset-password/" in outbox[0].get_content()


def test_forgot_password_unknown_email_sends_nothing(client, outbox):
    response = client.post(
        "/forgot-password", data={"email": "nobody@example.com"}, follow_redirects=True
    )
    assert b"a reset link is on its way" in response.data
    assert outbox == []


def test_reset_password_with_valid_token(client, db, flagged_ringer):
    token = make_reset_token(flagged_ringer)
    response = client.post(
        f"/reset-password/{token}",
        data={"new_password": NEW_PASSWORD, "confirm": NEW_PASSWORD},
        follow_redirects=True,
    )
    assert response.request.path == "/login"
    db.session.refresh(flagged_ringer)
    assert flagged_ringer.check_password(NEW_PASSWORD)
    assert flagged_ringer.must_change_password is False


def test_reset_token_is_single_use(client, ringer):
    token = make_reset_token(ringer)
    client.post(
        f"/reset-password/{token}",
        data={"new_password": NEW_PASSWORD, "confirm": NEW_PASSWORD},
    )
    response = client.get(f"/reset-password/{token}", follow_redirects=True)
    assert response.request.path == "/forgot-password"
    assert b"invalid or has expired" in response.data


def test_tampered_reset_token_rejected(client, ringer):
    token = make_reset_token(ringer)
    response = client.get(f"/reset-password/{token}x", follow_redirects=True)
    assert b"invalid or has expired" in response.data


def test_expired_reset_token_rejected(ringer):
    token = make_reset_token(ringer)
    assert verify_reset_token(token) == ringer
    assert verify_reset_token(token, max_age=-1) is None
