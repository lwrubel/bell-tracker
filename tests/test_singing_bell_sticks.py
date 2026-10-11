import re

import pytest
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import CHECKED_NOTES, Entry, EntryInstrument, InstrumentType, User


@pytest.fixture()
def stick_type(db):
    it = InstrumentType(
        name="Singing Bell Sticks", selection_mode="checkbox", enabled_by_default=True
    )
    db.session.add(it)
    db.session.commit()
    return it


def _entry_url(piece):
    return f"/pieces/{piece.id}/entry"


def _field(stick_type):
    return f"instrument_{stick_type.id}"


def _ringers(db, count):
    users = []
    for i in range(count):
        user = User(email=f"stick{i}@example.com", name=f"Stick {i}")
        user.set_password(RINGER_PASSWORD)
        users.append(user)
    db.session.add_all(users)
    db.session.commit()
    return users


def _tick(db, users, piece, stick_type):
    for i, user in enumerate(users):
        entry = Entry(user=user, piece=piece, position=f"P{i + 1}")
        db.session.add(entry)
        db.session.add(
            EntryInstrument(
                entry=entry, instrument_type=stick_type, notes=CHECKED_NOTES
            )
        )
    db.session.commit()


# --- ringer's equipment form ---------------------------------------------


def test_form_shows_a_plain_checkbox(client, db, ringer, program, stick_type):
    piece = add_piece(db, program, "Fanfare", 1)
    db.session.commit()
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(_entry_url(piece)).get_data(as_text=True)

    assert re.search(rf'<input[^>]*id="{_field(stick_type)}"[^>]*type="checkbox"', body)
    assert "<summary>Singing Bell Sticks</summary>" not in body
    assert "Show flats instead of sharps" not in body


def test_ticking_and_unticking_saves(client, db, ringer, program, stick_type):
    piece = add_piece(db, program, "Fanfare", 1)
    db.session.commit()
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(_entry_url(piece), data={_field(stick_type): "y"})
    db.session.expire_all()
    (selection,) = entry.instrument_selections
    assert selection.instrument_type == stick_type
    assert selection.notes == CHECKED_NOTES

    body = client.get(_entry_url(piece)).get_data(as_text=True)
    assert "checked" in body

    client.post(_entry_url(piece), data={})
    db.session.expire_all()
    assert entry.instrument_selections == []


def test_my_equipment_shows_yes(client, db, ringer, program, stick_type):
    piece = add_piece(db, program, "Fanfare", 1)
    db.session.commit()
    _tick(db, [ringer], piece, stick_type)

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/my-equipment").get_data(as_text=True)

    assert "Singing Bell Sticks" in body
    assert "Yes" in body


# --- reports -------------------------------------------------------------


def test_max_counts_is_the_most_ticked_on_one_piece(db, program, stick_type):
    first = add_piece(db, program, "First", 1)
    second = add_piece(db, program, "Second", 2)
    db.session.commit()
    users = _ringers(db, 3)
    _tick(db, users[:2], first, stick_type)
    _tick(db, users, second, stick_type)

    assert reports.checkbox_max_counts(program) == {stick_type: 3}


def test_max_counts_can_leave_out_special_pieces(db, program, stick_type):
    regular = add_piece(db, program, "Regular", 1)
    special = add_piece(db, program, "Encore", 2, special=True)
    db.session.commit()
    users = _ringers(db, 3)
    _tick(db, users[:1], regular, stick_type)
    _tick(db, users, special, stick_type)

    assert reports.checkbox_max_counts(program, include_special=False) == {
        stick_type: 1
    }


def test_max_counts_empty_when_nobody_ticked(program, stick_type):
    assert reports.checkbox_max_counts(program) == {}


def test_sticks_stay_out_of_pitch_reports(db, program, stick_type, instrument_type):
    piece = add_piece(db, program, "Fanfare", 1)
    db.session.commit()
    _tick(db, _ringers(db, 1), piece, stick_type)

    notes_by_type, mallets, _ = reports.equipment_table(program)
    assert notes_by_type == {}
    assert mallets == {}
    assert reports.cases_list(program) == {}
    assert reports.equipment_pull_list(program) == {}


@pytest.mark.parametrize("report", ["equipment-table", "equipment-pull-list"])
def test_report_pages_show_the_count(
    client, db, admin_user, program, stick_type, report
):
    first = add_piece(db, program, "First", 1)
    second = add_piece(db, program, "Second", 2)
    db.session.commit()
    users = _ringers(db, 2)
    _tick(db, users, first, stick_type)
    _tick(db, users[:1], second, stick_type)

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/{report}").get_data(as_text=True)

    assert "<h5>Singing Bell Sticks</h5>" in body
    assert "<p>2 <span" in body
