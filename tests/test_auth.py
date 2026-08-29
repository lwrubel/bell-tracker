from conftest import ADMIN_PASSWORD, login


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_with_valid_credentials_redirects_to_concerts(client, admin_user):
    response = login(client, admin_user, ADMIN_PASSWORD)
    assert response.status_code == 200
    assert response.request.path == "/concerts"


def test_login_with_wrong_password_shows_generic_error(client, admin_user):
    response = login(client, admin_user, "not-the-password")
    assert response.status_code == 200
    assert response.request.path == "/login"
    assert b"Invalid email or password" in response.data


def test_login_with_unknown_email_shows_same_generic_error(client):
    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "whatever"},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in response.data


def test_logout_requires_post(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get("/logout")
    assert response.status_code == 405


def test_logout_ends_session(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post("/logout")
    response = client.get("/concerts", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_redirected_to_login(client):
    response = client.get("/concerts", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
