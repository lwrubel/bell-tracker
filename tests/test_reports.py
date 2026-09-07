from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

from app import reports
from app.models import Case, Entry, EntryInstrument


def _sign_up(db, user, piece, instrument_type, notes):
    entry = Entry(user_id=user.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes)
    )
    db.session.commit()
    return entry


def test_packing_list_includes_only_cases_overlapping_used_pitches(
    db, ringer, concert, piece, instrument_type
):
    low_case = Case(
        instrument_type_id=instrument_type.id,
        case_number="C-LOW",
        note_range_low="C4",
        note_range_high="D4",
    )
    high_case = Case(
        instrument_type_id=instrument_type.id,
        case_number="C-HIGH",
        note_range_low="A4",
        note_range_high="C6",
    )
    db.session.add_all([low_case, high_case])
    db.session.commit()

    _sign_up(db, ringer, piece, instrument_type, "C4")

    result = reports.packing_list(concert)

    assert result == {instrument_type: [low_case]}


def test_packing_list_empty_when_nothing_signed_up(concert):
    assert reports.packing_list(concert) == {}


def test_equipment_table_groups_and_sorts_pitches_per_type(
    db, ringer, other_ringer, concert, piece, instrument_type
):
    _sign_up(db, ringer, piece, instrument_type, "E4,C4")
    entry2 = Entry(user_id=other_ringer.id, piece_id=piece.id, position="P2")
    db.session.add(entry2)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry2.id, instrument_type_id=instrument_type.id, notes="D4")
    )
    db.session.commit()

    notes_by_type, _, _ = reports.equipment_table(concert)

    assert notes_by_type[instrument_type] == ["C4", "D4", "E4"]


def test_equipment_table_misc_entries_only_include_nonblank_notes(
    db, ringer, other_ringer, concert, piece
):
    entry_with_misc = Entry(
        user_id=ringer.id, piece_id=piece.id, position="P1", misc_notes="extra mallets"
    )
    entry_blank = Entry(
        user_id=other_ringer.id, piece_id=piece.id, position="P2", misc_notes="   "
    )
    db.session.add_all([entry_with_misc, entry_blank])
    db.session.commit()

    _, _, misc_entries = reports.equipment_table(concert)

    assert misc_entries == [entry_with_misc]


def test_packing_list_route_requires_admin(client, ringer, concert):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}/reports/packing-list")
    assert response.status_code == 403


def test_packing_list_route_accessible_to_admin(client, admin_user, concert):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get(f"/concerts/{concert.id}/reports/packing-list")
    assert response.status_code == 200


def test_equipment_table_route_requires_admin(client, ringer, concert):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/concerts/{concert.id}/reports/equipment-table")
    assert response.status_code == 403


def test_reports_redirect_anonymous_to_login(client, concert):
    response = client.get(
        f"/concerts/{concert.id}/reports/packing-list", follow_redirects=False
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
