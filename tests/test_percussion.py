import re

import pytest
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import Entry, EntryInstrument, InstrumentOption, InstrumentType, User


@pytest.fixture()
def percussion(db):
    it = InstrumentType(name="Percussion", selection_mode="options")
    it.options = [
        InstrumentOption(name=name)
        for name in ("Triangle", "Slap Stick", "Jingle Bells")
    ]
    db.session.add(it)
    db.session.commit()
    return it


def _option(percussion, name):
    return next(o for o in percussion.options if o.name == name)


def _field(percussion):
    return f"instrument_{percussion.id}"


def _piece_with_percussion(db, program, percussion, title="Sleigh Ride", position=1):
    piece = add_piece(db, program, title, position)
    piece.instrument_types.append(percussion)
    db.session.commit()
    return piece


def _ringers(db, count):
    users = [User(email=f"perc{i}@example.com", name=f"Perc {i}") for i in range(count)]
    for user in users:
        user.set_password(RINGER_PASSWORD)
    db.session.add_all(users)
    db.session.commit()
    return users


def _pick(db, users, piece, percussion, *names):
    notes = ",".join(str(_option(percussion, n).id) for n in names)
    for i, user in enumerate(users):
        entry = Entry(user=user, piece=piece, position=f"P{i + 1}")
        db.session.add(entry)
        db.session.add(
            EntryInstrument(entry=entry, instrument_type=percussion, notes=notes)
        )
    db.session.commit()


# --- model ---------------------------------------------------------------


def test_options_are_listed_by_name(percussion):
    assert [o.name for o in percussion.options] == [
        "Jingle Bells",
        "Slap Stick",
        "Triangle",
    ]


def test_selected_options_skip_deleted_ones(db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    _pick(db, [ringer], piece, percussion, "Triangle", "Slap Stick")
    db.session.delete(_option(percussion, "Slap Stick"))
    db.session.commit()

    (selection,) = EntryInstrument.query.all()
    assert [o.name for o in selection.selected_options()] == ["Triangle"]


# --- ringer's equipment form ---------------------------------------------


def test_form_shows_a_checkbox_per_option(client, db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/pieces/{piece.id}/entry").get_data(as_text=True)

    assert "<summary>Percussion</summary>" in body
    for option in percussion.options:
        assert re.search(
            rf'<input[^>]*name="{_field(percussion)}"[^>]*type="checkbox"'
            rf'[^>]*value="{option.id}"',
            body,
        )
        assert f">{option.name}</label>" in body


def test_picking_options_saves_and_reloads(client, db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    triangle = _option(percussion, "Triangle")

    login(client, ringer, RINGER_PASSWORD)
    client.post(f"/pieces/{piece.id}/entry", data={_field(percussion): [triangle.id]})

    db.session.expire_all()
    (selection,) = entry.instrument_selections
    assert selection.selected_options() == [triangle]

    body = client.get(f"/pieces/{piece.id}/entry").get_data(as_text=True)
    assert re.search(rf'<input checked[^>]*value="{triangle.id}"', body)

    client.post(f"/pieces/{piece.id}/entry", data={})
    db.session.expire_all()
    assert entry.instrument_selections == []


def test_renaming_an_option_keeps_picks(db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    _pick(db, [ringer], piece, percussion, "Triangle")
    _option(percussion, "Triangle").name = "Large Triangle"
    db.session.commit()

    (selection,) = EntryInstrument.query.all()
    assert [o.name for o in selection.selected_options()] == ["Large Triangle"]


def test_my_equipment_lists_picked_options(client, db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    _pick(db, [ringer], piece, percussion, "Triangle", "Jingle Bells")

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/my-equipment").get_data(as_text=True)

    assert "Jingle Bells, Triangle" in body


# --- admin ---------------------------------------------------------------


def test_admin_adds_options_inline(client, db, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        "/admin/instrumenttype/new/",
        data={
            "display_order": 100,
            "name": "Shakers",
            "form_label": "",
            "selection_mode": "options",
            "note_range_low": "",
            "note_range_high": "",
            "position_prefix": "",
            "options-0-name": "Egg",
            "options-1-name": "Maraca",
        },
    )

    shakers = InstrumentType.query.filter_by(name="Shakers").one()
    assert shakers.selection_mode == "options"
    assert [o.name for o in shakers.options] == ["Egg", "Maraca"]


# --- reports -------------------------------------------------------------


def test_used_options_lists_each_option_picked_once_or_more(db, program, percussion):
    first = _piece_with_percussion(db, program, percussion, "First", 1)
    second = _piece_with_percussion(db, program, percussion, "Second", 2)
    users = _ringers(db, 3)
    _pick(db, users, first, percussion, "Triangle")
    _pick(db, users[:2], second, percussion, "Triangle", "Jingle Bells")

    assert reports.used_options(program) == {
        percussion: [
            _option(percussion, "Jingle Bells"),
            _option(percussion, "Triangle"),
        ]
    }


def test_used_options_can_leave_out_special_pieces(db, program, percussion):
    regular = _piece_with_percussion(db, program, percussion, "Regular", 1)
    special = _piece_with_percussion(db, program, percussion, "Encore", 2)
    special.special = True
    db.session.commit()
    users = _ringers(db, 2)
    _pick(db, users[:1], regular, percussion, "Triangle")
    _pick(db, users, special, percussion, "Triangle", "Slap Stick")

    assert reports.used_options(program, include_special=False) == {
        percussion: [_option(percussion, "Triangle")]
    }


def test_percussion_stays_out_of_pitch_reports(db, ringer, program, percussion):
    piece = _piece_with_percussion(db, program, percussion)
    _pick(db, [ringer], piece, percussion, "Triangle")

    notes_by_type, mallets, _ = reports.equipment_table(program)
    assert notes_by_type == {}
    assert mallets == {}
    assert reports.cases_list(program) == {}
    assert reports.equipment_pull_list(program) == {}
    assert reports.bass_bells(program)[0][1] == []


@pytest.mark.parametrize("report", ["equipment-table", "equipment-pull-list"])
def test_report_pages_list_used_options(
    client, db, admin_user, program, percussion, report
):
    piece = _piece_with_percussion(db, program, percussion)
    _pick(db, _ringers(db, 2), piece, percussion, "Triangle", "Jingle Bells")

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/{report}").get_data(as_text=True)

    assert "<h5>Percussion</h5>\n    <p>Jingle Bells, Triangle</p>" in body
    assert "Slap Stick" not in body
