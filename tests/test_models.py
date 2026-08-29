import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Entry, EntryInstrument, User


def test_password_is_hashed_not_stored_plaintext(db):
    user = User(email="a@example.com", name="A")
    user.set_password("secret123")
    assert user.password_hash != "secret123"
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False


def test_entry_is_unique_per_user_and_piece(db, ringer, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P2"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_different_ringers_can_share_a_piece(db, ringer, other_ringer, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.add(Entry(user_id=other_ringer.id, piece_id=piece.id, position="P2"))
    db.session.commit()  # should not raise

    assert Entry.query.filter_by(piece_id=piece.id).count() == 2


def test_entry_instrument_note_list_splits_on_comma():
    ei = EntryInstrument(notes="C4,E4,G4")
    assert ei.note_list() == ["C4", "E4", "G4"]


def test_entry_instrument_note_list_empty_when_no_notes():
    assert EntryInstrument(notes=None).note_list() == []
    assert EntryInstrument(notes="").note_list() == []


def test_deleting_piece_cascades_to_its_entries(db, ringer, piece):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    entry_id = entry.id

    db.session.delete(piece)
    db.session.commit()

    assert db.session.get(Entry, entry_id) is None
