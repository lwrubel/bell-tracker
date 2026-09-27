from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

from app import reports
from app.models import Case, Entry, EntryInstrument, Piece


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


def _special_piece(db, concert, instrument_type):
    special = Piece(
        concert_id=concert.id, title="Encore", program_order=2, special=True
    )
    special.instrument_types.append(instrument_type)
    db.session.add(special)
    db.session.commit()
    return special


def test_equipment_table_can_exclude_special_pieces(
    db, ringer, other_ringer, concert, piece, instrument_type, mallet_instrument_type
):
    special = _special_piece(db, concert, instrument_type)
    _sign_up(db, ringer, piece, instrument_type, "C4")
    special_entry = _sign_up(db, other_ringer, special, instrument_type, "G5")
    special_entry.misc_notes = "Bell tree"
    db.session.add(
        EntryInstrument(
            entry_id=special_entry.id,
            instrument_type_id=mallet_instrument_type.id,
            notes="Red yarn:2",
        )
    )
    db.session.commit()

    notes, mallets, misc = reports.equipment_table(concert)
    assert notes[instrument_type] == ["C4", "G5"]
    assert mallets[mallet_instrument_type] == {"Red yarn": 2}
    assert misc == [special_entry]
    assert special.id in reports.mallet_requirements(concert)

    notes, mallets, misc = reports.equipment_table(concert, include_special=False)
    assert notes[instrument_type] == ["C4"]
    assert mallet_instrument_type not in mallets
    assert misc == []
    assert reports.mallet_requirements(concert, include_special=False) == {}


def test_equipment_table_route_excludes_special_on_request(
    client, db, admin_user, ringer, concert, piece, instrument_type
):
    special = _special_piece(db, concert, instrument_type)
    _sign_up(db, ringer, special, instrument_type, "G5")
    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/concerts/{concert.id}/reports/equipment-table"

    included = client.get(url).get_data(as_text=True)
    assert "G5" in included
    assert "Exclude special pieces" in included

    excluded = client.get(url + "?special=exclude").get_data(as_text=True)
    assert "G5" not in excluded
    assert "Leaves out special pieces:" in excluded
    assert "Encore" in excluded


def test_equipment_table_hides_toggle_without_special_pieces(
    client, admin_user, concert, piece
):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get(f"/concerts/{concert.id}/reports/equipment-table")
    assert b"Exclude special pieces" not in response.data


def test_packing_list_can_exclude_special_pieces(
    client, db, admin_user, ringer, other_ringer, concert, piece, instrument_type
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
    special = _special_piece(db, concert, instrument_type)
    _sign_up(db, ringer, piece, instrument_type, "C4")
    _sign_up(db, other_ringer, special, instrument_type, "G5")

    assert reports.packing_list(concert) == {instrument_type: [high_case, low_case]}
    assert reports.packing_list(concert, include_special=False) == {
        instrument_type: [low_case]
    }

    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/concerts/{concert.id}/reports/packing-list"
    assert "C-HIGH" in client.get(url).get_data(as_text=True)
    excluded = client.get(url + "?special=exclude").get_data(as_text=True)
    assert "C-HIGH" not in excluded
    assert "Leaves out special pieces:" in excluded
