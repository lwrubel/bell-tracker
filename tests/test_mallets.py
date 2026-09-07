from conftest import RINGER_PASSWORD, login

from app import color, reports
from app.models import Entry, EntryInstrument, Piece


def _entry_url(concert, piece):
    return f"/concerts/{concert.id}/pieces/{piece.id}/entry"


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
    db, concert, mallet_instrument_type
):
    p = Piece(concert_id=concert.id, title="Fanfare", program_order=7)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_piece_added_through_a_concert_gets_color_types(
    db, concert, mallet_instrument_type
):
    # The Concert admin's inline form appends to concert.pieces rather than
    # calling session.add, so cover that path too.
    p = Piece(title="Prelude", program_order=8)
    concert.pieces.append(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_default_does_not_duplicate_an_explicit_selection(
    db, concert, mallet_instrument_type
):
    p = Piece(concert_id=concert.id, title="Chorale", program_order=9)
    p.instrument_types.append(mallet_instrument_type)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == [mallet_instrument_type]


def test_types_without_the_default_flag_are_not_enabled(db, concert, instrument_type):
    p = Piece(concert_id=concert.id, title="Interlude", program_order=10)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == []


def test_admin_can_remove_mallets_from_a_piece(db, concert, mallet_instrument_type):
    p = Piece(concert_id=concert.id, title="Aria", program_order=11)
    db.session.add(p)
    db.session.commit()
    assert p.instrument_types == [mallet_instrument_type]

    p.instrument_types.remove(mallet_instrument_type)
    db.session.commit()
    db.session.expire(p)

    assert p.instrument_types == []


# --- entry form --------------------------------------------------------


def test_entry_form_renders_a_number_field_per_color_plus_other(
    client, db, ringer, concert, mallet_piece, mallet_instrument_type
):
    db.session.add(Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, mallet_piece))

    assert response.status_code == 200
    assert b'type="number"' in response.data
    for i in range(len(color.MALLET_COLORS)):
        assert f'name="color_{mallet_instrument_type.id}_{i}"'.encode() in response.data
    assert f'name="other_{mallet_instrument_type.id}_label"'.encode() in response.data
    assert f'name="other_{mallet_instrument_type.id}_count"'.encode() in response.data
    # No pitch/flats toggle when the piece has only a color-mode type.
    assert b'id="flatToggle"' not in response.data


def test_submitting_counts_creates_entry_instrument_ordered_by_color_list(
    client, db, ringer, concert, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.post(
        _entry_url(concert, mallet_piece),
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
    client, db, ringer, concert, mallet_piece, mallet_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=mallet_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, mallet_piece),
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
    client, db, ringer, concert, mallet_piece, mallet_instrument_type
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
        _entry_url(concert, mallet_piece),
        data={_color_field(mallet_instrument_type, "Green yarn"): 0, "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections == []


def test_existing_counts_are_prepopulated_on_reload(
    client, db, ringer, concert, mallet_piece, mallet_instrument_type
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
    response = client.get(_entry_url(concert, mallet_piece))

    assert b'value="2"' in response.data
    assert b'value="soft bass"' in response.data
    assert b'value="3"' in response.data


# --- reports --------------------------------------------------------


def _sign_up_mallets(db, user, piece, instrument_type, notes):
    entry = Entry(user_id=user.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes
        )
    )
    db.session.commit()
    return entry


def test_mallet_requirements_sums_across_ringers_per_piece(
    db, ringer, other_ringer, concert, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")
    entry2 = Entry(user_id=other_ringer.id, piece_id=mallet_piece.id, position="P2")
    db.session.add(entry2)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry2.id,
            instrument_type_id=mallet_instrument_type.id,
            notes="Green yarn:3,Red yarn:1",
        )
    )
    db.session.commit()

    result = reports.mallet_requirements(concert)

    assert result == {mallet_piece.id: {"Green yarn": 5, "Red yarn": 1}}


def test_equipment_table_returns_mallet_totals_by_type(
    db, ringer, concert, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")

    notes_by_type, mallet_counts_by_type, _ = reports.equipment_table(concert)

    assert notes_by_type == {}
    assert mallet_counts_by_type == {mallet_instrument_type: {"Green yarn": 2}}


def test_packing_list_ignores_color_mode_types(
    db, ringer, concert, mallet_piece, mallet_instrument_type
):
    _sign_up_mallets(db, ringer, mallet_piece, mallet_instrument_type, "Green yarn:2")

    assert reports.packing_list(concert) == {}


def test_pitch_mode_entries_are_unchanged(
    client, db, ringer, concert, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, piece),
        data={f"instrument_{instrument_type.id}": ["C4", "E4"], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "C4,E4"
