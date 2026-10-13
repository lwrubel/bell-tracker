from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import Entry, EntryInstrument


def _assign(db, user, piece, position, notes=None, instrument_type=None):
    entry = Entry(user_id=user.id, piece_id=piece.id, position=position)
    db.session.add(entry)
    db.session.commit()
    if notes:
        db.session.add(
            EntryInstrument(
                entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes
            )
        )
        db.session.commit()
    return entry


def test_progress_grid_lays_out_entries_by_position_and_piece(
    db, ringer, other_ringer, program, piece, instrument_type
):
    second = add_piece(db, program, "Sleigh Ride", 2)
    db.session.commit()
    _assign(db, ringer, piece, "P1", "C4", instrument_type)
    _assign(db, other_ringer, piece, "Float")
    _assign(db, other_ringer, second, "LB1")

    pieces, rows, counts = reports.progress_grid(program.cycle)

    assert [p.title for p in pieces] == ["Ode to Joy", "Sleigh Ride"]
    assert [position for position, _ in rows][:4] == ["LB3", "LB2", "LB1", "P1"]
    grid = dict(rows)
    assert [[e.user for e in cell] for cell in grid["P1"]] == [[ringer], []]
    assert [[e.user for e in cell] for cell in grid["LB1"]] == [[], [other_ringer]]
    assert [[e.user for e in cell] for cell in grid["Float"]] == [[other_ringer], []]
    # Float isn't expected to enter equipment.
    assert counts == {piece.id: (1, 1), second.id: (0, 1)}


def test_progress_grid_counts_misc_notes_as_entered(db, ringer, program, piece):
    entry = _assign(db, ringer, piece, "P2")
    entry.misc_notes = "Bringing my own gloves"
    db.session.commit()

    _, _, counts = reports.progress_grid(program.cycle)

    assert counts[piece.id] == (1, 1)


def test_progress_report_marks_ringers_who_entered_equipment(
    client, db, admin_user, ringer, other_ringer, program, piece, instrument_type
):
    ringer.first_name = "Alice"
    other_ringer.first_name = "Ben"
    db.session.commit()
    _assign(db, ringer, piece, "P1", "C4", instrument_type)
    _assign(db, other_ringer, piece, "P2")
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.get(f"/admin/progress_report/?cycle_id={program.cycle_id}")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ode to Joy" in html
    assert "Alice &#10003;" in html
    assert "Ben &#10003;" not in html
    assert "1 / 2" in html


def test_progress_report_defaults_to_active_cycle(client, admin_user, cycle, piece):
    login(client, admin_user, ADMIN_PASSWORD)

    response = client.get("/admin/progress_report/")

    assert response.status_code == 200
    assert "Ode to Joy" in response.get_data(as_text=True)


def test_progress_report_is_admin_only(client, manager):
    login(client, manager, RINGER_PASSWORD)

    response = client.get("/admin/progress_report/", follow_redirects=False)

    assert response.status_code == 302
