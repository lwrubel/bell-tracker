from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login


def test_admin_index_redirects_anonymous_to_login(client):
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_index_redirects_non_admin_to_login(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_index_accessible_to_admin(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get("/admin/")
    assert response.status_code == 200


def test_entry_admin_view_accessible_to_admin(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get("/admin/entry/")
    assert response.status_code == 200


def test_entry_admin_view_blocked_for_ringer(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/admin/entry/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
