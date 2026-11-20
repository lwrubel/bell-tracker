from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login
from test_reports import _assign, _ringer, _type

from app import reports
from app.models import CHECKED_NOTES, InstrumentOption


def _conflicts(cycle):
    """equipment_conflicts flattened to names."""
    return [
        (
            piece.title,
            [
                (t.name, item, [(e.position, e.user.name) for e in entries])
                for t, item, entries in rows
            ],
        )
        for piece, rows in reports.equipment_conflicts(cycle)
    ]


def test_same_pitch_at_two_positions_on_a_piece_conflicts(
    db, program, piece, instrument_type
):
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    db.session.commit()
    _assign(db, users[0], piece, "P6", (instrument_type, "D5,E5,F5"))
    _assign(db, users[1], piece, "P5", (instrument_type, "D5,E5"))
    _assign(db, users[2], piece, "P7", (instrument_type, "G5"))

    assert _conflicts(program.cycle) == [
        (
            "Ode to Joy",
            [
                ("Chimes", "D5", [("P5", "Ringer 1"), ("P6", "Ringer 0")]),
                ("Chimes", "E5", [("P5", "Ringer 1"), ("P6", "Ringer 0")]),
            ],
        )
    ]


def test_same_pitch_on_different_pieces_is_fine(db, program, piece, instrument_type):
    later = add_piece(db, program, "Later", 2)
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(db, users[0], piece, "P5", (instrument_type, "D5"))
    _assign(db, users[1], later, "P6", (instrument_type, "D5"))

    assert _conflicts(program.cycle) == []


def test_main_bells_bass_bells_mallets_and_sticks_never_conflict(
    db, program, piece, bass_instrument_type, mallet_instrument_type
):
    main = _type(db, "Main Bells", note_range_low="C4", note_range_high="C8")
    sticks = _type(db, "Singing Bell Sticks", selection_mode="checkbox")
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    for user, position in zip(users, ("LB1", "LB2")):
        _assign(
            db,
            user,
            piece,
            position,
            (main, "C5"),
            (bass_instrument_type, "C3"),
            (mallet_instrument_type, "Red yarn:1"),
            (sticks, CHECKED_NOTES),
        )

    assert _conflicts(program.cycle) == []


def test_bass_chimes_bell_trees_and_percussion_conflict(db, program, piece):
    bass_chimes = _type(
        db, "Bass Chimes", note_range_low="C2", note_range_high="B3", display_order=15
    )
    tree = _type(
        db, "Bell Tree", note_range_low="C5", note_range_high="C8", keyboard_type=True
    )
    percussion = _type(db, "Percussion", selection_mode="options", display_order=200)
    percussion.options = [InstrumentOption(name=n) for n in ("Triangle", "Slap Stick")]
    db.session.commit()
    triangle = str(next(o.id for o in percussion.options if o.name == "Triangle"))
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    # Different pitches of one bell tree still mean one tree in two places.
    _assign(
        db, users[0], piece, "LB1", (bass_chimes, "A2"), (tree, "C5"), (percussion, triangle)
    )
    _assign(
        db, users[1], piece, "P3", (bass_chimes, "A2"), (tree, "G6"), (percussion, triangle)
    )

    assert _conflicts(program.cycle) == [
        (
            "Ode to Joy",
            [
                ("Bass Chimes", "A2", [("P3", "Ringer 1"), ("LB1", "Ringer 0")]),
                ("Bell Tree", "Bell Tree", [("P3", "Ringer 1"), ("LB1", "Ringer 0")]),
                ("Percussion", "Triangle", [("P3", "Ringer 1"), ("LB1", "Ringer 0")]),
            ],
        )
    ]


def test_ignores_instruments_removed_from_the_piece(
    db, program, piece, instrument_type
):
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(db, users[0], piece, "P5", (instrument_type, "D5"))
    _assign(db, users[1], piece, "P6", (instrument_type, "D5"))
    piece.instrument_types.remove(instrument_type)
    db.session.commit()

    assert _conflicts(program.cycle) == []


def test_conflicts_page(client, db, admin_user, program, piece, instrument_type):
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    first = _assign(db, users[0], piece, "P5", (instrument_type, "D5"))
    _assign(db, users[1], piece, "P6", (instrument_type, "D5"))
    login(client, admin_user, ADMIN_PASSWORD)

    assert "/admin/equipment_conflicts/" in client.get("/admin/").get_data(as_text=True)
    body = client.get("/admin/equipment_conflicts/").get_data(as_text=True)
    assert "Ode to Joy" in body
    assert "Chimes: D5" in body
    assert "P5 - D5/E5 &middot; Ringer 0" in body
    assert f"/admin/entry/equipment/?id={first.id}" in body


def test_conflicts_page_with_none(client, db, admin_user, program, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get("/admin/equipment_conflicts/").get_data(as_text=True)
    assert "No conflicts in Spring 2026." in body


def test_conflicts_page_is_admin_only(client, db, ringer, manager, program):
    for user in (ringer, manager):
        login(client, user, RINGER_PASSWORD)
        response = client.get("/admin/equipment_conflicts/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        client.post("/logout")
    assert "equipment_conflicts" not in client.get("/").get_data(as_text=True)
