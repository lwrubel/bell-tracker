import re

import pytest

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


@pytest.mark.parametrize(
    "url", ["/admin/", "/admin/instrumenttype/", "/admin/entry/"]
)
def test_admin_brand_links_to_the_front_end(client, admin_user, url):
    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(url).get_data(as_text=True)

    brand = re.search(r'<a class="navbar-brand" href="([^"]*)"', body)
    assert brand is not None, f"no navbar brand rendered on {url}"
    assert brand.group(1) == "/"


def test_front_end_home_is_reachable_from_the_admin_brand(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200


def _entries_for_two_ringers(db, ringer, other_ringer, piece):
    from app.models import Entry

    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.add(Entry(user_id=other_ringer.id, piece_id=piece.id, position="P2"))
    db.session.commit()


# Not the full name: the search box echoes the term back into the page.
@pytest.mark.parametrize("term", ["One", "ringer@example.com"])
def test_entry_admin_search_finds_one_ringers_entries(
    client, db, admin_user, ringer, other_ringer, piece, term
):
    _entries_for_two_ringers(db, ringer, other_ringer, piece)
    login(client, admin_user, ADMIN_PASSWORD)

    body = client.get("/admin/entry/", query_string={"search": term}).get_data(
        as_text=True
    )

    assert "Ringer One" in body
    assert "Ringer Two" not in body


def test_entry_admin_list_sorts_by_ringer(
    client, db, admin_user, ringer, other_ringer, piece
):
    # Alphabetically first, though added second.
    other_ringer.name = "Abby Two"
    _entries_for_two_ringers(db, ringer, other_ringer, piece)
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.get("/admin/entry/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.index("Abby Two") < body.index("Ringer One")
