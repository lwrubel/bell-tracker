from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import Case, Entry, EntryInstrument, InstrumentType


def _sign_up(db, user, piece, instrument_type, notes):
    entry = Entry(user_id=user.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes)
    )
    db.session.commit()
    return entry


def test_cases_list_includes_only_cases_overlapping_used_pitches(
    db, ringer, program, piece, instrument_type
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

    result = reports.cases_list(program)

    assert result == {instrument_type: [low_case]}


def test_cases_list_includes_case_matched_only_by_second_range(
    client, db, admin_user, ringer, program, piece, instrument_type
):
    split_case = Case(
        instrument_type_id=instrument_type.id,
        case_number="C-SPLIT",
        note_range_low="C4",
        note_range_high="D4",
        second_range_low="A5",
        second_range_high="C6",
    )
    db.session.add(split_case)
    db.session.commit()

    _sign_up(db, ringer, piece, instrument_type, "B5")

    assert reports.cases_list(program) == {instrument_type: [split_case]}

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/cases-list").get_data(
        as_text=True
    )
    assert "C-SPLIT (C4-D4, A5-C6)" in body


def test_cases_list_empty_when_nothing_signed_up(program):
    assert reports.cases_list(program) == {}


def _main_bells_with_cases(db):
    main_bells = InstrumentType(
        name="Main Bells", note_range_low="C4", note_range_high="C8", display_order=0
    )
    db.session.add(main_bells)
    db.session.commit()
    cases = [
        Case(
            instrument_type_id=main_bells.id,
            case_number=number,
            note_range_low=low,
            note_range_high=high,
        )
        for number, low, high in [
            ("B10", "C#8", "G8"),
            ("B3", "C4", "F#4"),
            ("B1", "C5", "C6"),
        ]
    ]
    db.session.add_all(cases)
    db.session.commit()
    return main_bells, cases


def test_cases_list_always_lists_every_main_bells_case(db, program):
    main_bells, cases = _main_bells_with_cases(db)

    result = reports.cases_list(program)

    assert list(result) == [main_bells]
    assert [c.case_number for c in result[main_bells]] == ["B1", "B3", "B10"]


def test_cases_list_always_lists_every_bass_bells_case(
    db, program, bass_instrument_type
):
    bass_case = Case(
        instrument_type_id=bass_instrument_type.id,
        case_number="LB1",
        note_range_low="C2",
        note_range_high="B2",
    )
    db.session.add(bass_case)
    db.session.commit()

    assert reports.cases_list(program) == {bass_instrument_type: [bass_case]}


def test_cases_list_puts_main_bells_first_alongside_signed_up_cases(
    client, db, admin_user, ringer, program, piece, instrument_type
):
    main_bells, _ = _main_bells_with_cases(db)
    chime_case = Case(
        instrument_type_id=instrument_type.id,
        case_number="C-1",
        note_range_low="C4",
        note_range_high="C5",
    )
    db.session.add(chime_case)
    db.session.commit()
    _sign_up(db, ringer, piece, instrument_type, "C4")

    result = reports.cases_list(program)

    assert list(result) == [main_bells, instrument_type]

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/cases-list").get_data(
        as_text=True
    )
    assert "B1 (C5-C6)" in body
    assert "B3 (C4-F#4)" in body


def test_equipment_table_groups_and_sorts_pitches_per_type(
    db, ringer, other_ringer, program, piece, instrument_type
):
    _sign_up(db, ringer, piece, instrument_type, "E4,C4")
    entry2 = Entry(user_id=other_ringer.id, piece_id=piece.id, position="P2")
    db.session.add(entry2)
    db.session.commit()
    db.session.add(
        EntryInstrument(entry_id=entry2.id, instrument_type_id=instrument_type.id, notes="D4")
    )
    db.session.commit()

    notes_by_type, _, _ = reports.equipment_table(program)

    assert notes_by_type[instrument_type] == ["C4", "D4", "E4"]


def test_equipment_table_leaves_out_main_bells(
    db, ringer, program, piece, instrument_type
):
    main_bells = InstrumentType(
        name="Main Bells", note_range_low="C4", note_range_high="C8"
    )
    db.session.add(main_bells)
    db.session.commit()
    other = add_piece(db, program, "Main Bells piece", 9)
    db.session.commit()
    _sign_up(db, ringer, other, main_bells, "C5")
    _sign_up(db, ringer, piece, instrument_type, "C4")

    notes_by_type, _, _ = reports.equipment_table(program)

    assert list(notes_by_type) == [instrument_type]


def test_equipment_table_misc_entries_only_include_nonblank_notes(
    db, ringer, other_ringer, program, piece
):
    entry_with_misc = Entry(
        user_id=ringer.id, piece_id=piece.id, position="P1", misc_notes="extra mallets"
    )
    entry_blank = Entry(
        user_id=other_ringer.id, piece_id=piece.id, position="P2", misc_notes="   "
    )
    db.session.add_all([entry_with_misc, entry_blank])
    db.session.commit()

    _, _, misc_entries = reports.equipment_table(program)

    assert misc_entries == [entry_with_misc]


def test_cases_list_route_requires_admin(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/cases-list")
    assert response.status_code == 403


def test_cases_list_route_accessible_to_admin(client, admin_user, program):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/cases-list")
    assert response.status_code == 200


def test_equipment_table_route_requires_admin(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/equipment-table")
    assert response.status_code == 403


def test_reports_redirect_anonymous_to_login(client, program):
    response = client.get(
        f"/programs/{program.id}/reports/cases-list", follow_redirects=False
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- equipment pull list ------------------------------------------------


def _case(db, instrument_type, number, low, high, **kwargs):
    case = Case(
        instrument_type_id=instrument_type.id,
        case_number=number,
        note_range_low=low,
        note_range_high=high,
        **kwargs,
    )
    db.session.add(case)
    db.session.commit()
    return case


def test_equipment_pull_list_lists_bells_needed_from_each_case(
    db, ringer, other_ringer, program, piece, instrument_type
):
    low = _case(db, instrument_type, "C1", "C4", "B4")
    high = _case(db, instrument_type, "C2", "C5", "C6")
    _case(db, instrument_type, "C3", "C#6", "C6")  # nothing used from this one
    _sign_up(db, ringer, piece, instrument_type, "E4,C5,C4")
    _sign_up(db, other_ringer, piece, instrument_type, "C4,G5")

    result = reports.equipment_pull_list(program)

    assert result == {
        instrument_type: ([(low, ["C4", "E4"]), (high, ["C5", "G5"])], [])
    }


def test_equipment_pull_list_reports_pitches_no_case_covers(
    db, ringer, program, piece, instrument_type
):
    case = _case(db, instrument_type, "C1", "C4", "D4")
    _sign_up(db, ringer, piece, instrument_type, "C4,G5")

    assert reports.equipment_pull_list(program) == {
        instrument_type: ([(case, ["C4"])], ["G5"])
    }


def test_equipment_pull_list_leaves_out_main_and_bass_bells(
    db, ringer, program, piece, instrument_type
):
    for name in ("Main Bells", "Bass Bells"):
        excluded = InstrumentType(name=name, note_range_low="C2", note_range_high="C8")
        db.session.add(excluded)
        db.session.commit()
        _case(db, excluded, f"{name[0]}1", "C4", "C5")
        other = add_piece(db, program, f"{name} piece", 5 + len(name))
        db.session.commit()
        _sign_up(db, ringer, other, excluded, "C4")
    _case(db, instrument_type, "C1", "C4", "C5")
    _sign_up(db, ringer, piece, instrument_type, "C4")

    assert list(reports.equipment_pull_list(program)) == [instrument_type]


def test_equipment_pull_list_ignores_color_mode_types(
    db, ringer, program, mallet_piece, mallet_instrument_type
):
    _sign_up(db, ringer, mallet_piece, mallet_instrument_type, "Red yarn:2")
    assert reports.equipment_pull_list(program) == {}


def test_equipment_pull_list_only_counts_this_programs_pieces(
    db, ringer, cycle, program, piece, instrument_type
):
    from app.models import Program

    _case(db, instrument_type, "C1", "C4", "C5")
    _sign_up(db, ringer, piece, instrument_type, "C4")
    other_program = Program(cycle=cycle, name="Other")
    db.session.add(other_program)
    db.session.commit()

    assert reports.equipment_pull_list(other_program) == {}


def test_equipment_pull_list_route_is_admin_only(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    url = f"/programs/{program.id}/reports/equipment-pull-list"
    assert client.get(url).status_code == 403


def test_equipment_pull_list_page(client, db, admin_user, program, piece, instrument_type):
    _case(db, instrument_type, "C1", "C4", "D4")
    _sign_up(db, admin_user, piece, instrument_type, "D4,C4,A6")

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/equipment-pull-list").get_data(
        as_text=True
    )

    assert "Equipment Pull List" in body
    assert "<strong>C1</strong>: C4, D4" in body
    assert "Not in any case: A6" in body
    home = client.get("/").get_data(as_text=True)
    assert f"/programs/{program.id}/reports/equipment-pull-list" in home


# --- bass bells -----------------------------------------------------------


def _assign(db, user, piece, position, *selections):
    entry = Entry(user_id=user.id, piece_id=piece.id, position=position)
    db.session.add(entry)
    db.session.commit()
    for instrument_type, notes in selections:
        db.session.add(
            EntryInstrument(
                entry_id=entry.id, instrument_type_id=instrument_type.id, notes=notes
            )
        )
    db.session.commit()
    return entry


def test_bass_bells_lists_each_pieces_lb_positions_and_their_bells(
    db, ringer, other_ringer, program, piece, instrument_type, bass_instrument_type
):
    later = add_piece(db, program, "Later Piece", 2)
    db.session.commit()
    lb2 = _assign(db, ringer, piece, "LB2", (bass_instrument_type, "E3,C3"))
    lb1 = _assign(
        db,
        other_ringer,
        piece,
        "LB1",
        (bass_instrument_type, "G2"),
        (instrument_type, "C4"),
    )
    _assign(db, ringer, later, "P1", (instrument_type, "C4"))

    result = reports.bass_bells(program)

    assert [(pp.piece, positions) for pp, positions in result] == [
        (
            piece,
            [
                (lb1, [(bass_instrument_type, ["G2"]), (instrument_type, ["C4"])]),
                (lb2, [(bass_instrument_type, ["C3", "E3"])]),
            ],
        ),
        (later, []),
    ]


def test_bass_bells_route_is_admin_only(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    url = f"/programs/{program.id}/reports/bass-bells"
    assert client.get(url).status_code == 403


def test_bass_bells_page(client, db, admin_user, ringer, program, piece, bass_instrument_type):
    _assign(db, ringer, piece, "LB1", (bass_instrument_type, "D3,C3"))
    add_piece(db, program, "No Bass", 2)
    db.session.commit()

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/bass-bells").get_data(
        as_text=True
    )

    assert "<h1>Bass Bells</h1>" in body
    assert "1. Ode to Joy" in body
    assert "<strong>LB1</strong> (Ringer One)" in body
    assert "<li>Bass Bells: C3, D3</li>" in body
    assert "2. No Bass" in body
    assert "No LB positions." in body
    home = client.get("/").get_data(as_text=True)
    assert f"/programs/{program.id}/reports/bass-bells" in home
