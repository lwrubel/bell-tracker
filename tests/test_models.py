import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Case, Entry, EntryInstrument, User
from conftest import ADMIN_PASSWORD, login


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


def test_single_range_case_has_one_range():
    case = Case(case_number="1", note_range_low="C4", note_range_high="D4")
    assert case.ranges() == [("C4", "D4")]
    assert case.range_label() == "C4-D4"
    assert case.covers("C#4") is True
    assert case.covers("E4") is False


def test_two_range_case_covers_both_ranges():
    case = Case(
        case_number="2",
        note_range_low="C4",
        note_range_high="D4",
        second_range_low="A5",
        second_range_high="C6",
    )
    assert case.ranges() == [("C4", "D4"), ("A5", "C6")]
    assert case.range_label() == "C4-D4, A5-C6"
    assert case.covers("D4") is True
    assert case.covers("B5") is True
    assert case.covers("G5") is False


def _post_case(client, instrument_type, **ranges):
    data = {
        "case_number": "K-1",
        "instrument_type": instrument_type.id,
        "note_range_low": "C4",
        "note_range_high": "D4",
        "second_range_low": "",
        "second_range_high": "",
    }
    data.update(ranges)
    return client.post("/admin/case/new/", data=data, follow_redirects=True)


def test_admin_can_create_two_range_case(client, db, admin_user, instrument_type):
    login(client, admin_user, ADMIN_PASSWORD)
    _post_case(client, instrument_type, second_range_low="A5", second_range_high="C6")
    case = Case.query.one()
    assert case.ranges() == [("C4", "D4"), ("A5", "C6")]


def test_admin_single_range_case_stores_null_second_range(
    client, db, admin_user, instrument_type
):
    login(client, admin_user, ADMIN_PASSWORD)
    _post_case(client, instrument_type)
    case = Case.query.one()
    assert case.second_range_low is None
    assert case.second_range_high is None


@pytest.mark.parametrize(
    "ranges",
    [
        {"second_range_low": "A5"},  # half filled
        {"second_range_low": "A5", "second_range_high": "C7"},  # past type range
        {"second_range_low": "C6", "second_range_high": "A5"},  # low above high
        {"note_range_low": "D4", "note_range_high": "C4"},  # first range reversed
    ],
)
def test_admin_rejects_invalid_case_ranges(
    client, db, admin_user, instrument_type, ranges
):
    login(client, admin_user, ADMIN_PASSWORD)
    _post_case(client, instrument_type, **ranges)
    assert Case.query.count() == 0
