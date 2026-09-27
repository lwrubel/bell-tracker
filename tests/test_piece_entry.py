from conftest import RINGER_PASSWORD, login

from app.models import Entry, EntryInstrument


def _entry_url(concert, piece):
    return f"/concerts/{concert.id}/pieces/{piece.id}/entry"


def test_entry_form_404s_when_ringer_has_no_entry(client, ringer, concert, piece):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))
    assert response.status_code == 404


def test_entry_form_404s_for_float_position(client, db, ringer, concert, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="Float"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))
    assert response.status_code == 404


def test_entry_form_renders_pitch_checkboxes_for_enabled_instrument_types(
    client, db, ringer, concert, piece, instrument_type
):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))

    assert response.status_code == 200
    assert b'type="checkbox"' in response.data
    assert b'value="C4"' in response.data


def test_entry_form_links_back_to_concert(client, db, ringer, concert, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))

    assert f'href="/concerts/{concert.id}"'.encode() in response.data


def test_submitting_pitches_creates_entry_instrument(
    client, db, ringer, concert, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.post(
        _entry_url(concert, piece),
        data={
            f"instrument_{instrument_type.id}": ["C4", "E4"],
            "misc_notes": "extra mallets",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    db.session.refresh(entry)
    assert entry.misc_notes == "extra mallets"
    selection = entry.instrument_selections[0]
    assert selection.notes == "C4,E4"


def test_pitches_are_stored_as_sharps_regardless_of_display(
    client, db, ringer, concert, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, piece),
        data={f"instrument_{instrument_type.id}": ["C#4"], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections[0].notes == "C#4"


def test_resubmitting_with_no_pitches_deletes_the_selection(
    client, db, ringer, concert, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry.id, instrument_type_id=instrument_type.id, notes="C4")
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(
        _entry_url(concert, piece),
        data={f"instrument_{instrument_type.id}": [], "misc_notes": ""},
        follow_redirects=True,
    )

    db.session.refresh(entry)
    assert entry.instrument_selections == []


def test_existing_selections_are_prepopulated_on_reload(
    client, db, ringer, concert, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry.id, instrument_type_id=instrument_type.id, notes="C4,E4")
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))

    assert b'value="C4"' in response.data
    assert b"checked" in response.data


def test_ringer_cannot_fill_in_another_ringers_entry(
    client, db, ringer, other_ringer, concert, piece
):
    db.session.add(Entry(user_id=other_ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_entry_url(concert, piece))
    assert response.status_code == 404
