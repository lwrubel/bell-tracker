from conftest import RINGER_PASSWORD, add_piece, login

from app.models import Entry, EntryInstrument


def _url(program):
    return f"/programs/{program.id}/my-equipment"


def test_home_page_links_to_each_programs_equipment_list(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/")
    assert b"View my equipment" in response.data
    assert _url(program).encode() in response.data


def test_equipment_list_links_back_home_and_offers_print(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_url(program))
    assert b'href="/"' in response.data
    assert b"window.print()" in response.data


def test_requires_login(client, program):
    response = client.get(_url(program))
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_404s_for_unknown_program(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    assert client.get("/programs/9999/my-equipment").status_code == 404


def test_lists_position_and_equipment_per_piece(
    client, db, ringer, program, piece, instrument_type, mallet_instrument_type
):
    entry = Entry(
        user_id=ringer.id, piece_id=piece.id, position="P3", misc_notes="Bell tree"
    )
    db.session.add(entry)
    db.session.add_all(
        [
            EntryInstrument(
                entry=entry, instrument_type_id=instrument_type.id, notes="C4,D#4"
            ),
            EntryInstrument(
                entry=entry,
                instrument_type_id=mallet_instrument_type.id,
                notes="Red yarn:2",
            ),
        ]
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(_url(program)).get_data(as_text=True)

    assert "Ode to Joy" in body
    assert "P3" in body
    assert "Chimes" in body
    assert "C4, D#4" in body
    assert "Red yarn ×2" in body
    assert "Bell tree" in body


def test_piece_without_equipment_says_so(client, db, ringer, program, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(_url(program)).get_data(as_text=True)

    assert "P1" in body
    assert "No equipment selected" in body


def test_only_shows_own_pieces(client, db, ringer, other_ringer, program, piece):
    other_piece = add_piece(db, program, "Carol of the Bells", 2)
    db.session.add(other_piece)
    db.session.flush()
    db.session.add_all(
        [
            Entry(user_id=ringer.id, piece_id=piece.id, position="P1"),
            Entry(
                user_id=other_ringer.id,
                piece_id=other_piece.id,
                position="P2",
                misc_notes="Someone else's gear",
            ),
        ]
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(_url(program)).get_data(as_text=True)

    assert "Ode to Joy" in body
    assert "Carol of the Bells" not in body
    assert "Someone else" not in body
