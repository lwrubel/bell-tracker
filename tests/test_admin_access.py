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


def test_entry_admin_edits_misc_notes(client, db, admin_user, ringer, piece):
    from app.models import Entry

    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.post(
        f"/admin/entry/edit/?id={entry.id}",
        data={
            "user": str(ringer.id),
            "piece": str(piece.id),
            "position": "P1",
            "misc_notes": "Bell tree",
        },
    )

    assert response.status_code == 302
    db.session.refresh(entry)
    assert entry.misc_notes == "Bell tree"


def _entry_with_pitches(db, ringer, piece, instrument_type, notes):
    from app.models import Entry, EntryInstrument

    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.flush()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes
        )
    )
    db.session.commit()
    return entry


def test_entry_admin_equipment_page_shows_saved_selections(
    client, db, admin_user, ringer, piece, instrument_type
):
    entry = _entry_with_pitches(db, ringer, piece, instrument_type, "C4,E4")
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.get(f"/admin/entry/equipment/?id={entry.id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert re.search(r'<input[^>]*checked[^>]*value="C4"', body)
    assert not re.search(r'<input[^>]*checked[^>]*value="D4"', body)


def test_entry_admin_edits_instrument_selections(
    client, db, admin_user, ringer, piece, instrument_type
):
    entry = _entry_with_pitches(db, ringer, piece, instrument_type, "C4,E4")
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.post(
        f"/admin/entry/equipment/?id={entry.id}",
        data={f"instrument_{instrument_type.id}": ["D4"], "misc_notes": "Gloves"},
    )

    assert response.status_code == 302
    db.session.refresh(entry)
    assert [s.notes for s in entry.instrument_selections] == ["D4"]
    assert entry.misc_notes == "Gloves"


def test_entry_admin_clearing_selections_removes_them(
    client, db, admin_user, ringer, piece, instrument_type
):
    entry = _entry_with_pitches(db, ringer, piece, instrument_type, "C4")
    login(client, admin_user, ADMIN_PASSWORD)

    client.post(f"/admin/entry/equipment/?id={entry.id}", data={"misc_notes": ""})

    db.session.refresh(entry)
    assert entry.instrument_selections == []


def test_entry_admin_equipment_page_404s_for_missing_entry(client, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get("/admin/entry/equipment/?id=999999")
    assert response.status_code == 404


def test_entry_admin_equipment_page_blocked_for_ringer(
    client, db, ringer, piece, instrument_type
):
    entry = _entry_with_pitches(db, ringer, piece, instrument_type, "C4")
    login(client, ringer, RINGER_PASSWORD)

    response = client.post(
        f"/admin/entry/equipment/?id={entry.id}",
        data={f"instrument_{instrument_type.id}": ["D4"]},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "C4"


def test_entry_admin_links_to_equipment_page(
    client, db, admin_user, ringer, piece, instrument_type
):
    entry = _entry_with_pitches(db, ringer, piece, instrument_type, "C4")
    login(client, admin_user, ADMIN_PASSWORD)

    list_body = client.get("/admin/entry/").get_data(as_text=True)
    edit_body = client.get(f"/admin/entry/edit/?id={entry.id}").get_data(as_text=True)

    assert f"/admin/entry/equipment/?id={entry.id}" in list_body
    assert f"/admin/entry/equipment/?id={entry.id}" in edit_body
