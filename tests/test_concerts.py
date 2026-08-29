from conftest import RINGER_PASSWORD, login

from app.models import Entry, Piece


def test_index_redirects_to_concerts(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/concerts")


def test_concerts_index_lists_concerts(client, ringer, concert):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/concerts")
    assert response.status_code == 200
    assert concert.name.encode() in response.data


def test_concert_detail_only_shows_pieces_ringer_is_assigned_to(
    client, db, ringer, concert, instrument_type
):
    assigned = Piece(concert_id=concert.id, title="Assigned Piece", program_order=1)
    unassigned = Piece(concert_id=concert.id, title="Unassigned Piece", program_order=2)
    db.session.add_all([assigned, unassigned])
    db.session.commit()
    db.session.add(Entry(user_id=ringer.id, piece_id=assigned.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}")

    assert b"Assigned Piece" in response.data
    assert b"Unassigned Piece" not in response.data


def test_concert_detail_shows_position(client, db, ringer, concert, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="LB2"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}")

    assert b"LB2" in response.data


def test_float_position_has_no_entry_link(client, db, ringer, concert, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="Float"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}")

    assert b"Float" in response.data
    entry_url = f"/concerts/{concert.id}/pieces/{piece.id}/entry".encode()
    assert entry_url not in response.data


def test_ringer_does_not_see_another_ringers_entries(
    client, db, ringer, other_ringer, concert, piece
):
    db.session.add(Entry(user_id=other_ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}")

    assert piece.title.encode() not in response.data


def test_concert_detail_404s_for_unknown_concert(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/concerts/999999")
    assert response.status_code == 404
