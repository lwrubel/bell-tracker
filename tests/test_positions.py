import pytest
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

from app.models import Entry
from app.positions import POSITION_CODES, position_label


@pytest.mark.parametrize(
    "code, label",
    [
        ("P1", "P1 - C4/D4"),
        ("P2", "P2 - E4/F4"),
        ("P3", "P3 - G4/A4"),
        ("P4", "P4 - B4/C5"),
        ("P10", "P10 - G6/A6"),
        ("P11", "P11 - B6/C7"),
    ],
)
def test_treble_positions_show_base_notes(code, label):
    assert position_label(code) == label


@pytest.mark.parametrize("code", ["LB1", "LB2", "LB3", "Float", "Other"])
def test_positions_without_notes_show_bare_code(code):
    assert position_label(code) == code


def test_every_p_position_has_base_notes():
    for code in POSITION_CODES:
        if code.startswith("P"):
            assert position_label(code) != code


def test_ringer_pages_show_position_label(client, db, ringer, concert, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P2"))
    db.session.commit()
    login(client, ringer, RINGER_PASSWORD)

    for url in (
        f"/concerts/{concert.id}",
        f"/concerts/{concert.id}/pieces/{piece.id}/entry",
        f"/concerts/{concert.id}/my-equipment",
    ):
        assert "P2 - E4/F4" in client.get(url).get_data(as_text=True), url


def test_admin_entry_views_show_position_label(client, db, admin_user, ringer, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P3"))
    db.session.commit()
    login(client, admin_user, ADMIN_PASSWORD)

    assert "P3 - G4/A4" in client.get("/admin/entry/").get_data(as_text=True)
    form = client.get("/admin/entry/new/").get_data(as_text=True)
    assert '<option value="P3">P3 - G4/A4</option>' in form
