from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import (
    CHECKED_NOTES,
    Case,
    Entry,
    EntryInstrument,
    InstrumentType,
    Program,
    User,
)


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


def _bass_chimes(db):
    bass_chimes = InstrumentType(
        name="Bass Chimes", note_range_low="C2", note_range_high="B3", display_order=15
    )
    db.session.add(bass_chimes)
    db.session.commit()
    return bass_chimes


def test_equipment_by_pitch_sorts_pitches_into_sections(
    db, program, piece, instrument_type, bass_instrument_type
):
    bass_chimes = _bass_chimes(db)
    later = add_piece(db, program, "Later", 2)
    db.session.commit()
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    db.session.commit()
    # Which position rings a pitch doesn't matter, only the pitch. Bass Bells
    # are always set out, so Bass Equipment lists only the extras.
    _assign(
        db,
        users[0],
        piece,
        "LB1",
        (bass_instrument_type, "D3,E3"),
        (bass_chimes, "A2"),
    )
    _assign(db, users[1], piece, "P8", (instrument_type, "D#4,E4"))
    _assign(db, users[1], later, "P3", (instrument_type, "C4,F#4,C#7"))
    _assign(db, users[2], later, "Float", (instrument_type, "C4"))

    assert reports.equipment_by_pitch(program) == [
        ("Bass Equipment", [(bass_chimes, ["A2"])]),
        ("C4/D4", [(instrument_type, ["C4", "D#4"])]),
        ("E4/F4", [(instrument_type, ["E4", "F#4"])]),
        ("B6/C7", [(instrument_type, ["C#7"])]),
    ]


def test_equipment_by_pitch_leaves_out_bass_bells(
    db, ringer, program, piece, bass_instrument_type
):
    _assign(db, ringer, piece, "LB1", (bass_instrument_type, "G2,C3,C4"))

    assert reports.equipment_by_pitch(program) == []


def test_equipment_by_pitch_folds_d7_and_up_an_octave_and_stops_at_c8(
    db, ringer, program, piece
):
    high = InstrumentType(name="Chimes High", note_range_low="C6", note_range_high="C9")
    db.session.add(high)
    db.session.commit()
    _assign(db, ringer, piece, "P11", (high, "D6,D7,E7,F#7,B7,C8,C#8,C9"))

    assert reports.equipment_by_pitch(program) == [
        ("C6/D6", [(high, ["D6", "D7"])]),
        ("E6/F6", [(high, ["E7", "F#7"])]),
        ("B6/C7", [(high, ["B7", "C8"])]),
    ]


def test_equipment_by_pitch_lists_types_in_display_order(
    db, ringer, program, piece, instrument_type
):
    bass_chimes = _bass_chimes(db)
    _assign(db, ringer, piece, "LB1", (instrument_type, "B3"), (bass_chimes, "B3"))

    assert reports.equipment_by_pitch(program) == [
        ("Bass Equipment", [(bass_chimes, ["B3"]), (instrument_type, ["B3"])])
    ]


def test_equipment_by_pitch_leaves_out_main_bells_and_non_pitch_types(
    db, ringer, program, piece, instrument_type, mallet_instrument_type
):
    main_bells = InstrumentType(
        name="Main Bells", note_range_low="C4", note_range_high="C8"
    )
    sticks = InstrumentType(name="Singing Bell Sticks", selection_mode="checkbox")
    db.session.add_all([main_bells, sticks])
    db.session.commit()
    _assign(
        db,
        ringer,
        piece,
        "P1",
        (main_bells, "C4,D4"),
        (instrument_type, "C5"),
        (mallet_instrument_type, "Green yarn:2"),
        (sticks, CHECKED_NOTES),
    )

    assert reports.equipment_by_pitch(program) == [
        ("B4/C5", [(instrument_type, ["C5"])])
    ]


def test_equipment_table_page_lists_pitch_sections(
    client, db, admin_user, ringer, program, piece, instrument_type
):
    _assign(db, ringer, piece, "P5", (instrument_type, "E4,C4,C#4"))

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/equipment-table").get_data(
        as_text=True
    )

    assert "By Pitch" not in body
    assert "<h5>C4/D4</h5>" in body
    assert "<strong>Chimes:</strong> C4, C#4" in body
    assert "<h5>E4/F4</h5>" in body
    assert "<h5>D5/E5</h5>" not in body


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

    assert reports.misc_entries(program) == [entry_with_misc]


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


# --- cover sheets --------------------------------------------------------


def _ringer(db, name):
    user = User(email=f"{name.lower().replace(' ', '.')}@example.com", name=name)
    user.set_password(RINGER_PASSWORD)
    db.session.add(user)
    return user


def _cover_sheet_entries(db, piece):
    """Ringers on `piece` across P, LB, Other and Float positions."""
    entries = {}
    for name, position in [
        ("Pat Ten", "P10"),
        ("Lee Bass", "LB1"),
        ("Olive Other", "Other"),
        ("Fay Float", "Float"),
        ("Ann Two", "P2"),
        ("Bea Float", "Float"),
    ]:
        entry = Entry(user=_ringer(db, name), piece=piece, position=position)
        db.session.add(entry)
        entries[name] = entry
    db.session.commit()
    return entries


def test_cover_sheets_orders_by_roster_and_leaves_out_lb(db, program, piece):
    entries = _cover_sheet_entries(db, piece)

    [(program_piece, ringers, floats)] = reports.cover_sheets(program)

    assert program_piece.piece == piece
    assert ringers == [entries["Ann Two"], entries["Pat Ten"], entries["Olive Other"]]
    assert floats == [entries["Bea Float"], entries["Fay Float"]]


def test_cover_sheets_lists_each_program_piece_even_when_empty(db, program, piece):
    other = add_piece(db, program, "Empty Piece", 2)
    db.session.commit()

    sheets = reports.cover_sheets(program)

    assert [(pp.piece, r, f) for pp, r, f in sheets] == [
        (piece, [], []),
        (other, [], []),
    ]


def test_cover_sheets_route_shows_ringers_and_equipment(
    client, db, admin_user, program, piece, instrument_type
):
    entries = _cover_sheet_entries(db, piece)
    stick_type = InstrumentType(
        name="Singing Bell Sticks",
        form_label="Singing Bell Stick",
        selection_mode="checkbox",
    )
    db.session.add(stick_type)
    ann = entries["Ann Two"]
    ann.misc_notes = "Bell tree"
    db.session.add_all(
        [
            EntryInstrument(entry=ann, instrument_type=instrument_type, notes="C4,E4"),
            EntryInstrument(entry=ann, instrument_type=stick_type, notes=CHECKED_NOTES),
        ]
    )
    db.session.commit()

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/cover-sheets").get_data(
        as_text=True
    )

    assert "Ode to Joy" in body
    assert "P2 - E4/F4" in body
    assert "Ann Two" in body
    assert "<strong>Chimes:</strong> C4, E4" in body
    assert "Singing Bell Stick" in body
    assert "<strong>Misc:</strong> Bell tree" in body
    assert "Lee Bass" not in body
    assert '<span class="sheet-label">Float</span>Bea Float, Fay Float' in body


# --- bass bell cover sheets ------------------------------------------------


def _bass_sheet_program(db, program, piece, bass_instrument_type, instrument_type):
    """Three pieces where bells stay put, move between LB positions, come
    from a treble position, and come off the floor."""
    lb1, lb2, p5, mallets = (
        _ringer(db, name) for name in ("Lee One", "Lou Two", "Pat Five", "Mal Lets")
    )
    db.session.commit()
    second = add_piece(db, program, "Second", 2)
    third = add_piece(db, program, "Third", 3)
    mallet_type = InstrumentType(name="Mallets", selection_mode="color")
    db.session.add(mallet_type)
    db.session.commit()

    entries = {
        "first lb1": _assign(db, lb1, piece, "LB1", (bass_instrument_type, "C3,D3")),
        "first lb2": _assign(db, lb2, piece, "LB2", (bass_instrument_type, "E3")),
        "first p5": _assign(db, p5, piece, "P5", (instrument_type, "C4")),
        "second lb1": _assign(
            db,
            lb1,
            second,
            "LB1",
            (bass_instrument_type, "E3,C3,G2"),
            (instrument_type, "C4"),
            (mallet_type, "Yellow:2"),
        ),
        "second lb2": _assign(db, lb2, second, "LB2", (bass_instrument_type, "D3")),
        "third lb1": _assign(db, lb1, third, "LB1", (bass_instrument_type, "D3")),
    }
    return second, third, mallet_type, entries


def test_bass_bell_cover_sheets_traces_where_each_bell_comes_from(
    db, program, piece, bass_instrument_type, instrument_type
):
    second, third, mallet_type, entries = _bass_sheet_program(
        db, program, piece, bass_instrument_type, instrument_type
    )
    empty = add_piece(db, program, "No Bass", 4)
    db.session.commit()

    result = reports.bass_bell_cover_sheets(program)
    by_piece = {pp.piece: rows for pp, rows in result}

    assert [pp.piece for pp, _ in result] == [piece, second, third, empty]
    floor = "Coming from Floor"
    lb1_first = [(bass_instrument_type, ["C3", "D3"])]
    lb2_first = [(bass_instrument_type, ["E3"])]
    assert by_piece[piece] == [
        (entries["first lb1"], lb1_first, [(floor, lb1_first)], []),
        (entries["first lb2"], lb2_first, [(floor, lb2_first)], []),
    ]
    [lb1_row, lb2_row] = by_piece[second]
    assert lb1_row[0] == entries["second lb1"]
    assert lb1_row[1] == [
        (bass_instrument_type, ["G2", "C3", "E3"]),
        (instrument_type, ["C4"]),
    ]
    assert lb1_row[2] == [
        ("Already here", [(bass_instrument_type, ["C3"])]),
        ("Coming from LB2", [(bass_instrument_type, ["E3"])]),
        ("Coming from P5", [(instrument_type, ["C4"])]),
        (floor, [(bass_instrument_type, ["G2"])]),
    ]
    assert [s.instrument_type for s in lb1_row[3]] == [mallet_type]
    assert lb2_row[2] == [("Coming from LB1", [(bass_instrument_type, ["D3"])])]
    # D3 was LB2's on Second, so it moves; nothing waits on the floor.
    d3 = [(bass_instrument_type, ["D3"])]
    assert by_piece[third] == [(entries["third lb1"], d3, [("Coming from LB2", d3)], [])]
    assert by_piece[empty] == []


def test_bass_bell_cover_sheets_leaves_unused_bells_where_they_were(
    db, ringer, other_ringer, program, piece, bass_instrument_type
):
    """A bell nobody rings on a piece stays with whoever last used it, even
    when that position is empty on the piece in between."""
    second = add_piece(db, program, "Second", 2)
    third = add_piece(db, program, "Third", 3)
    db.session.commit()
    _assign(db, ringer, piece, "LB1", (bass_instrument_type, "C3"))
    _assign(db, other_ringer, piece, "LB2", (bass_instrument_type, "E3"))
    _assign(db, ringer, second, "LB1", (bass_instrument_type, "D3"))
    lb1 = _assign(db, ringer, third, "LB1", (bass_instrument_type, "C3,E3,F3"))

    result = reports.bass_bell_cover_sheets(program)

    assert result[2][1] == [
        (
            lb1,
            [(bass_instrument_type, ["C3", "E3", "F3"])],
            [
                ("Already here", [(bass_instrument_type, ["C3"])]),
                ("Coming from LB2", [(bass_instrument_type, ["E3"])]),
                ("Coming from Floor", [(bass_instrument_type, ["F3"])]),
            ],
            [],
        )
    ]


def test_bass_bell_cover_sheets_page(
    client, db, admin_user, program, piece, bass_instrument_type, instrument_type
):
    _bass_sheet_program(db, program, piece, bass_instrument_type, instrument_type)
    add_piece(db, program, "No Bass", 4)
    db.session.commit()

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(
        f"/programs/{program.id}/reports/bass-bell-cover-sheets"
    ).get_data(as_text=True)

    assert "<h1>Bass Bell Cover Sheets</h1>" in body
    assert body.index("Bells needed:") < body.index("Already here:")
    assert '<div class="bell-line">G2, C3, E3</div>' in body
    assert '<div class="bell-line"><strong>Chimes:</strong> C4</div>' in body
    assert "Bass Bells:" not in body
    for label in (
        "Already here:",
        "Coming from LB2:",
        "Coming from P5:",
        "Coming from Floor:",
    ):
        assert f'<span class="sheet-label">{label}</span>' in body
    assert '<div class="bell-line">C3, D3</div>' in body
    assert "<strong>Mallets:</strong> Yellow ×2" in body
    assert "Pat Five" not in body
    assert "No LB positions." in body


def test_bass_bell_cover_sheets_access(
    client, db, ringer, other_ringer, manager, admin_user, program, piece, cycle
):
    url = f"/programs/{program.id}/reports/bass-bell-cover-sheets"
    other_program = Program(cycle=cycle, name="Other Concert")
    db.session.add(other_program)
    db.session.commit()
    other_piece = add_piece(db, other_program, "Elsewhere", 1)
    db.session.commit()
    _assign(db, ringer, piece, "LB2")
    _assign(db, other_ringer, piece, "P3")
    _assign(db, other_ringer, other_piece, "LB1")

    for user, password, status in [
        (ringer, RINGER_PASSWORD, 200),
        (other_ringer, RINGER_PASSWORD, 403),
        (manager, RINGER_PASSWORD, 200),
        (admin_user, ADMIN_PASSWORD, 200),
    ]:
        login(client, user, password)
        assert client.get(url).status_code == status, user.name
        home = client.get("/").get_data(as_text=True)
        assert (url in home) == (status == 200), user.name
        client.post("/logout")
