from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import color, reports
from app.models import Entry, EntryInstrument, Piece


def _entry_url(piece):
    return f"/pieces/{piece.id}/entry"


def _color_field(mallet_instrument_type, label):
    return f"color_{mallet_instrument_type.id}_{color.MALLET_COLORS.index(label)}"


# --- app/color.py --------------------------------------------------------


def test_format_and_parse_round_trip():
    encoded = color.format_color_counts([("Green yarn", 2), ("Red yarn", 1)])
    assert encoded == "Green yarn:2,Red yarn:1"
    assert color.parse_color_counts(encoded) == [("Green yarn", 2), ("Red yarn", 1)]


def test_format_drops_zero_and_non_positive():
    assert color.format_color_counts(
        [("Green yarn", 0), ("Red yarn", None), ("Blue yarn", 3)]
    ) == "Blue yarn:3"


def test_sanitize_label_strips_delimiters():
    assert color.sanitize_label("big, soft: mallet") == "big  soft  mallet"


def test_parse_ignores_malformed_chunks():
    assert color.parse_color_counts("Green yarn:2,junk,Red yarn:notint,:5") == [
        ("Green yarn", 2)
    ]


def test_other_label_survives_round_trip():
    label = color.OTHER_PREFIX + color.sanitize_label("soft bass")
    encoded = color.format_color_counts([(label, 3)])
    assert color.parse_color_counts(encoded) == [("Other: soft bass", 3)]


# --- enabled by default on new pieces ------------------------------------


def test_new_piece_gets_color_types_automatically(
    db, program, mallet_instrument_type
):
    p = add_piece(db, program, "Fanfare", 7)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_piece_added_through_a_cycle_gets_color_types(
    db, cycle, mallet_instrument_type
):
    # A piece appended through a relationship reaches the session by
    # cascade rather than session.add, so cover that path too.
    p = Piece(title="Prelude")
    cycle.pieces.append(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_default_does_not_duplicate_an_explicit_selection(
    db, program, mallet_instrument_type
):
    p = add_piece(db, program, "Chorale", 9)
    p.instrument_types.append(mallet_instrument_type)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_types_without_the_default_flag_are_not_enabled(db, program, instrument_type):
    p = add_piece(db, program, "Interlude", 10)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == []


def test_admin_can_remove_mallets_from_a_piece(db, program, mallet_instrument_type):
    p = add_piece(db, program, "Aria", 11)
    db.session.add(p)
    db.session.commit()
    assert p.instrument_types == [mallet_instrument_type]

    p.instrument_types.remove(mallet_instrument_type)
    db.session.commit()
    db.session.expire(p)

    assert p.instrument_types == []


# --- entry form --------------------------------------------------------


def test_entry_form_renders_a_number_field_per_color_plus_other(
    client, db, ringer, program, mallet_piece, mallet_instrument_type
):
    db.session.add(Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(mallet_piece))

    assert response.status_code == 200
    assert b'type="number"' in response.data
    for i in range(len(color.MALLET_COLORS)):
        assert f'name="color_{mallet_instrument_type.id}_{i}"'.encode() in response.data
    assert f'name="other_{mallet_instrument_type.id}_label"'.encode() in response.data
    assert f'name="other_{mallet_instrument_type.id}_count"'.encode() in response.data
    # No pitch/flats toggle when the piece has only a color-mode type.
    assert b'id="flatToggle"' not in response.data


def test_submitting_counts_creates_entry_instrument_ordered_by_color_list(
    client, db, ringer, program, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.post(
        _entry_url(mallet_piece),
        data={
            _color_field(mallet_instrument_type, "Green yarn"): 2,
            _color_field(mallet_instrument_type, "Red yarn"): 1,
            "misc_notes": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "Red yarn:1,Green yarn:2"


def test_other_row_is_stored_and_sanitized(
    client, db, ringer, program, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(mallet_piece),
        data={
            f"other_{mallet_instrument_type.id}_label": "soft, bass: mallet",
            f"other_{mallet_instrument_type.id}_count": 3,
            "misc_notes": "",
        },
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "Other: soft  bass  mallet:3"


def test_blank_submit_creates_no_selection_and_deletes_existing(
    client, db, ringer, program, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id,
            instrument_type_id=mallet_instrument_type.id,
            notes="Green yarn:2",
        )
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(mallet_piece),
        data={_color_field(mallet_instrument_type, "Green yarn"): 0, "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections == []


def test_existing_counts_are_prepopulated_on_reload(
    client, db, ringer, program, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id,
            instrument_type_id=mallet_instrument_type.id,
            notes="Green yarn:2,Other: soft bass:3",
        )
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(mallet_piece))

    assert b'value="2"' in response.data
    assert b'value="soft bass"' in response.data
    assert b'value="3"' in response.data


# --- reports --------------------------------------------------------


def _sign_up_mallets(db, user, piece, instrument_type, notes, position="P1"):
    entry = Entry(user_id=user.id, piece_id=piece.id, position=position)
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes
        )
    )
    db.session.commit()
    return entry


def test_mallet_max_counts_takes_the_most_on_any_one_piece(
    db, ringer, other_ringer, program, mallet_piece, mallet_instrument_type
):
    later = add_piece(db, program, "Later", 5)
    later.instrument_types.append(mallet_instrument_type)
    db.session.commit()
    # Mallet Piece: 5 green (2 + 3), 1 red. Later: 4 green, 2 red, 1 other.
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")
    _sign_up_mallets(
        db, other_ringer, mallet_piece, mallet_instrument_type, "Green yarn:3,Red yarn:1",
        position="P2",
    )
    _sign_up_mallets(
        db, ringer, later, mallet_instrument_type,
        "Green yarn:4,Red yarn:2,Other: soft bass:1",
    )

    assert reports.mallet_max_counts(program) == [
        ("Red yarn", 2),
        ("Green yarn", 5),
        ("Other: soft bass", 1),
    ]


def test_equipment_table_page_lists_mallet_counts(
    client, db, admin_user, ringer, program, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/equipment-table").get_data(
        as_text=True
    )

    assert "<h2>Mallets</h2>" in body
    assert "<li>Green yarn: 2</li>" in body
    assert "Per Piece" not in body
    assert "Toccata" not in body


def test_mallets_stay_out_of_equipment_by_pitch(
    db, ringer, program, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")

    assert reports.equipment_by_pitch(program) == []


def test_cases_list_ignores_color_mode_types(
    db, ringer, program, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")

    assert reports.cases_list(program) == {}


def test_pitch_mode_entries_are_unchanged(
    client, db, ringer, program, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(piece),
        data={f"instrument_{instrument_type.id}": ["C4", "E4"], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "C4,E4"


def test_ringer_views_do_not_show_other_ringers_mallets(
    client, db, ringer, other_ringer, program, mallet_piece, mallet_instrument_type
):
    """Mallets are a per-position choice, so a ringer's own pages must not
    surface the piece-wide total across everyone on the piece."""
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")
    entry2 = Entry(user_id=other_ringer.id, piece_id=mallet_piece.id, position="P2")
    db.session.add(entry2)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry2.id,
            instrument_type_id=mallet_instrument_type.id,
            notes="Red yarn:7",
        )
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)

    program = client.get(f"/cycles/{program.cycle_id}").get_data(as_text=True)
    assert "Red yarn" not in program
    assert "&times;2" not in program

    form = client.get(_entry_url(mallet_piece)).get_data(as_text=True)
    assert "Red yarn &times;7" not in form
    assert "all ringers" not in form
