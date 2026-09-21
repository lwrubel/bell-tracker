import pytest
from conftest import RINGER_PASSWORD, login

from app import positions, reports
from app.models import Entry, EntryInstrument, Piece


@pytest.fixture()
def bass_piece(db, concert, instrument_type, bass_instrument_type):
    """A piece with an unrestricted type (Chimes) plus Bass Bells, which the
    enabled_by_default flag attaches on its own."""
    p = Piece(concert_id=concert.id, title="Bass Piece", program_order=3)
    p.instrument_types.append(instrument_type)
    db.session.add(p)
    db.session.commit()
    return p


def _entry_url(concert, piece):
    return f"/concerts/{concert.id}/pieces/{piece.id}/entry"


def _open_entry_as(client, db, ringer, concert, piece, position):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position=position))
    db.session.commit()
    login(client, ringer, RINGER_PASSWORD)
    return client.get(_entry_url(concert, piece))


# --- who sees what -------------------------------------------------------


@pytest.mark.parametrize("position", ["LB1", "LB2", "LB3"])
def test_lb_positions_see_bass_bells(
    client, db, ringer, concert, bass_piece, bass_instrument_type, position
):
    response = _open_entry_as(client, db, ringer, concert, bass_piece, position)

    assert response.status_code == 200
    assert f'name="instrument_{bass_instrument_type.id}"'.encode() in response.data
    assert b'value="C2"' in response.data


@pytest.mark.parametrize("position", ["P1", "P11", "Aux"])
def test_non_lb_positions_do_not_see_bass_bells(
    client, db, ringer, concert, bass_piece, bass_instrument_type, position
):
    response = _open_entry_as(client, db, ringer, concert, bass_piece, position)

    assert response.status_code == 200
    assert f'name="instrument_{bass_instrument_type.id}"'.encode() not in response.data
    assert b'value="C2"' not in response.data


@pytest.mark.parametrize("position", ["LB1", "P1"])
def test_unrestricted_types_stay_visible_to_every_position(
    client, db, ringer, concert, bass_piece, instrument_type, position
):
    response = _open_entry_as(client, db, ringer, concert, bass_piece, position)

    assert f'name="instrument_{instrument_type.id}"'.encode() in response.data


# --- saving --------------------------------------------------------------


def test_lb_ringer_can_save_bass_bell_pitches(
    client, db, ringer, concert, bass_piece, bass_instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=bass_piece.id, position="LB1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, bass_piece),
        data={f"instrument_{bass_instrument_type.id}": ["C2", "G2"], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    by_type = {s.instrument_type_id: s.notes for s in entry.instrument_selections}
    assert by_type[bass_instrument_type.id] == "C2,G2"


def test_saving_from_a_non_lb_position_keeps_a_hidden_bass_bells_row(
    client, db, ringer, concert, bass_piece, instrument_type, bass_instrument_type
):
    # The ringer signed up at LB1, then an admin moved them to P1. Their bass
    # bells row is now hidden - saving the form must not silently delete it.
    entry = Entry(user_id=ringer.id, piece_id=bass_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id,
            instrument_type_id=bass_instrument_type.id,
            notes="C2,G2",
        )
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, bass_piece),
        data={f"instrument_{instrument_type.id}": ["C4"], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    by_type = {s.instrument_type_id: s.notes for s in entry.instrument_selections}
    assert by_type[bass_instrument_type.id] == "C2,G2"
    assert by_type[instrument_type.id] == "C4"


# --- enabled_by_default --------------------------------------------------


def test_bass_bells_is_enabled_on_a_new_piece(db, concert, bass_instrument_type):
    p = Piece(concert_id=concert.id, title="Postlude", program_order=12)
    db.session.add(p)
    db.session.commit()

    assert p.instrument_types == [bass_instrument_type]


def test_bass_bells_is_enabled_on_a_piece_added_through_a_concert(
    db, concert, bass_instrument_type
):
    p = Piece(title="Offertory", program_order=13)
    concert.pieces.append(p)
    db.session.commit()

    assert p.instrument_types == [bass_instrument_type]


# --- ordering ------------------------------------------------------------


def test_bass_bells_is_listed_before_the_general_types(
    client, db, ringer, concert, bass_piece, bass_instrument_type, instrument_type
):
    """The type a ringer only sees because of their position goes first.

    bass_piece attaches Chimes explicitly and picks up Bass Bells from
    enabled_by_default afterwards, so the piece lists them in that order -
    the form has to put Bass Bells on top regardless.
    """
    response = _open_entry_as(client, db, ringer, concert, bass_piece, "LB1")
    body = response.get_data(as_text=True)

    assert body.index(f"instrument_{bass_instrument_type.id}") < body.index(
        f"instrument_{instrument_type.id}"
    )


def test_ordering_puts_position_specific_types_first(
    db, ringer, bass_piece, bass_instrument_type, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=bass_piece.id, position="LB1")
    db.session.add(entry)
    db.session.commit()

    assert entry.visible_instrument_types()[0] is bass_instrument_type


def test_ordering_leaves_the_general_types_alone(
    db, ringer, bass_piece, bass_instrument_type, instrument_type
):
    """A ringer who can't see bass bells gets the piece's own order."""
    entry = Entry(user_id=ringer.id, piece_id=bass_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    visible = entry.visible_instrument_types()

    assert bass_instrument_type not in visible
    assert visible == [t for t in bass_piece.instrument_types if t in visible]


# --- supporting pieces ---------------------------------------------------


def test_position_prefixes_are_derived_from_the_position_codes():
    assert positions.position_prefixes() == ["P", "LB", "Float", "Aux"]


def test_reports_still_count_a_hidden_types_selections(
    db, ringer, concert, bass_piece, bass_instrument_type
):
    # Visibility is presentation only; the equipment table is for the admin
    # laying gear out, so a row hidden from its own ringer still counts.
    entry = Entry(user_id=ringer.id, piece_id=bass_piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(
            entry_id=entry.id, instrument_type_id=bass_instrument_type.id, notes="C2"
        )
    )
    db.session.commit()

    notes_by_type, _, _ = reports.equipment_table(concert)

    assert notes_by_type[bass_instrument_type] == ["C2"]
