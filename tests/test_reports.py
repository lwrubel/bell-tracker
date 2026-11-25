from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app import reports
from app.models import (
    CHECKED_NOTES,
    Case,
    Entry,
    EntryInstrument,
    InstrumentOption,
    InstrumentType,
    Program,
    User,
)


def _on_piece(piece, instrument_type):
    """Put `instrument_type` on `piece`, as a ringer can only sign up for
    the piece's own instruments."""
    if instrument_type not in piece.instrument_types:
        piece.instrument_types.append(instrument_type)


def _sign_up(db, user, piece, instrument_type, notes):
    _on_piece(piece, instrument_type)
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


def test_bell_trees_are_listed_apart_from_the_pitch_sections(
    db, ringer, other_ringer, program, piece, instrument_type
):
    smb_tree = InstrumentType(
        name="SMB Bell Tree",
        note_range_low="C5",
        note_range_high="C#7",
        display_order=75,
        keyboard_type=True,
    )
    tree = InstrumentType(
        name="Bell Tree",
        note_range_low="C5",
        note_range_high="C8",
        display_order=85,
        keyboard_type=True,
    )
    db.session.add_all([smb_tree, tree])
    db.session.commit()
    later = add_piece(db, program, "Later", 2)
    db.session.commit()
    _assign(db, ringer, piece, "P5", (tree, "E5,C5"), (instrument_type, "C5"))
    _assign(db, other_ringer, piece, "P6", (smb_tree, "G5"))
    _assign(db, ringer, later, "P5", (tree, "C5,G6"))

    assert reports.equipment_by_pitch(program) == [
        ("B4/C5", [(instrument_type, ["C5"])])
    ]
    assert reports.bell_trees(program) == [
        (smb_tree, ["G5"]),
        (tree, ["C5", "E5", "G6"]),
    ]


def test_equipment_table_page_lists_bell_trees_last(
    client, db, admin_user, ringer, program, piece
):
    tree = InstrumentType(
        name="Bell Tree", note_range_low="C5", note_range_high="C8", keyboard_type=True
    )
    db.session.add(tree)
    db.session.commit()
    _assign(db, ringer, piece, "P5", (tree, "E5,C5"))

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/equipment-table").get_data(
        as_text=True
    )

    assert "<h5>Bell Tree</h5>\n  <p>C5, E5</p>" in body
    assert body.index("<h2>Bell Trees</h2>") > body.index("Miscellaneous")
    assert "B4/C5" not in body


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


def test_equipment_table_route_open_to_ringers(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/equipment-table")
    assert response.status_code == 200


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


def test_equipment_pull_list_route_open_to_ringers(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    url = f"/programs/{program.id}/reports/equipment-pull-list"
    assert client.get(url).status_code == 200


def test_equipment_pull_list_page(client, db, admin_user, program, piece, instrument_type):
    _case(db, instrument_type, "C1", "C4", "D4")
    _sign_up(db, admin_user, piece, instrument_type, "D4,C4,A6")

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/equipment-pull-list").get_data(
        as_text=True
    )

    assert "Equipment Pull List" in body
    assert "<strong>C1:</strong> C4, D4" in body
    assert "<strong>Not in any case:</strong> A6" in body
    home = client.get("/").get_data(as_text=True)
    assert f"/programs/{program.id}/reports/equipment-pull-list" in home


# --- bass bells -----------------------------------------------------------


def _assign(db, user, piece, position, *selections):
    entry = Entry(user_id=user.id, piece_id=piece.id, position=position)
    db.session.add(entry)
    db.session.commit()
    for instrument_type, notes in selections:
        _on_piece(piece, instrument_type)
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


def test_bass_bells_route_is_closed_to_ringers(client, ringer, program):
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
    assert ringers == [
        (entries["Ann Two"], []),
        (entries["Pat Ten"], []),
        (entries["Olive Other"], []),
    ]
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
    piece.instrument_types.append(stick_type)
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


def _skip_cover_sheet(db, program, piece):
    for program_piece in program.program_pieces:
        if program_piece.piece_id == piece.id:
            program_piece.cover_sheet = False
    db.session.commit()


def test_cover_sheets_leave_out_pieces_without_one(
    client, db, admin_user, program, piece
):
    skipped = add_piece(db, program, "No Sheet Piece", 2)
    db.session.commit()
    _skip_cover_sheet(db, program, skipped)

    assert [pp.piece for pp, _, _ in reports.cover_sheets(program)] == [piece]

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/cover-sheets").get_data(
        as_text=True
    )
    assert piece.title in body
    assert "No Sheet Piece" not in body
    # It's still in the program everywhere else.
    order = client.get(f"/programs/{program.id}/order").get_data(as_text=True)
    assert "No Sheet Piece" in order


def test_bass_bell_cover_sheets_skip_a_piece_but_still_follow_its_bells(
    db, program, piece, bass_instrument_type, instrument_type
):
    second, third, _, entries = _bass_sheet_program(
        db, program, piece, bass_instrument_type, instrument_type
    )
    _skip_cover_sheet(db, program, second)

    result = reports.bass_bell_cover_sheets(program)

    assert [pp.piece for pp, _ in result] == [piece, third]
    # D3 still moved to LB2 on the skipped second piece.
    d3 = [(bass_instrument_type, ["D3"])]
    assert dict((pp.piece, rows) for pp, rows in result)[third] == [
        (entries["third lb1"], d3, [("Coming from LB2", d3)], [])
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


def test_reports_leave_out_instruments_removed_from_the_piece(
    client, db, admin_user, ringer, program, piece, instrument_type
):
    _case(db, instrument_type, "C1", "C4", "C6")
    _sign_up(db, ringer, piece, instrument_type, "C4,D4")
    piece.instrument_types.remove(instrument_type)
    db.session.commit()

    assert reports.equipment_by_pitch(program) == []
    assert reports.equipment_pull_list(program) == {}
    assert reports.cases_list(program) == {}
    [(program_piece, [(entry, [])], [])] = reports.cover_sheets(program)
    assert entry.sorted_instrument_selections() == []


def test_admin_ticks_keyboard_type_to_list_a_new_tree_on_its_own(
    client, db, admin_user, ringer, program, piece, instrument_type
):
    login(client, admin_user, ADMIN_PASSWORD)
    form = client.get("/admin/instrumenttype/new/").get_data(as_text=True)
    assert "Keyboard type" in form
    client.post(
        "/admin/instrumenttype/new/",
        data={
            "display_order": 80,
            "name": "SMB Bell Tree (Brian's bells)",
            "form_label": "",
            "selection_mode": "pitch",
            "note_range_low": "C5",
            "note_range_high": "C7",
            "position_prefix": "",
            "keyboard_type": "y",
        },
    )
    brians = InstrumentType.query.filter_by(name="SMB Bell Tree (Brian's bells)").one()
    assert brians.keyboard_type is True

    _assign(db, ringer, piece, "P5", (brians, "G5,C5"), (instrument_type, "C5"))

    assert reports.equipment_by_pitch(program) == [
        ("B4/C5", [(instrument_type, ["C5"])])
    ]
    assert reports.bell_trees(program) == [(brians, ["C5", "G5"])]


# --- starting placement --------------------------------------------------


def _type(db, name, **kwargs):
    instrument_type = InstrumentType(name=name, **kwargs)
    db.session.add(instrument_type)
    db.session.commit()
    return instrument_type


def _placement(program):
    """starting_placement with types and items flattened to names."""
    return [
        (label, [(t.name, items) for t, items in types])
        for label, types in reports.starting_placement(program)
    ]


def test_starting_placement_puts_each_bell_where_it_is_first_used(
    db, program, piece, instrument_type
):
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    later = add_piece(db, program, "Later", 2)
    db.session.commit()
    # Ode to Joy first: P5 uses C5 and D5. Later, P8 also uses C5 (stays
    # at P5) and adds C6.
    _assign(db, users[0], piece, "P5", (instrument_type, "D5,C5"))
    _assign(db, users[1], later, "P8", (instrument_type, "C5,C6"))
    # Same piece, same pitch: the lower position gets it.
    _assign(db, users[2], piece, "P6", (instrument_type, "D5,E5"))

    assert _placement(program) == [
        ("P5 - D5/E5", [("Chimes", ["C5", "D5"])]),
        ("P6 - F5/G5", [("Chimes", ["E5"])]),
        ("P8 - C6/D6", [("Chimes", ["C6"])]),
    ]


def test_starting_placement_leaves_out_main_and_bass_bells_and_bass_chimes(
    db, program, piece, instrument_type, bass_instrument_type
):
    main = _type(db, "Main Bells", note_range_low="C4", note_range_high="C8")
    bass_chimes = _type(db, "Bass Chimes", note_range_low="C2", note_range_high="B3")
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(db, users[0], piece, "P1", (main, "C4"), (instrument_type, "D4"))
    _assign(
        db, users[1], piece, "LB1", (bass_instrument_type, "C3"), (bass_chimes, "A2")
    )

    assert _placement(program) == [("P1 - C4/D4", [("Chimes", ["D4"])])]


def test_starting_placement_puts_a_whole_bell_tree_at_its_first_user(
    db, program, piece
):
    tree = _type(
        db, "Bell Tree", note_range_low="C5", note_range_high="C8", keyboard_type=True
    )
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    later = add_piece(db, program, "Later", 2)
    db.session.commit()
    _assign(db, users[0], piece, "P7", (tree, "E5"))
    _assign(db, users[1], later, "P3", (tree, "C5,G6"))

    assert _placement(program) == [("P7 - A5/B5", [("Bell Tree", ["C5", "E5", "G6"])])]


def test_starting_placement_counts_mallets_and_sticks_per_position(
    db, program, piece, mallet_instrument_type
):
    sticks = _type(
        db,
        "Singing Bell Sticks",
        form_label="Singing Bell Stick",
        selection_mode="checkbox",
    )
    percussion = _type(db, "Percussion", selection_mode="options")
    percussion.options = [InstrumentOption(name=n) for n in ("Triangle", "Slap Stick")]
    db.session.commit()
    ids = {o.name: str(o.id) for o in percussion.options}
    triangle, slap = ids["Triangle"], ids["Slap Stick"]
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    later = add_piece(db, program, "Later", 2)
    db.session.commit()
    _assign(
        db,
        users[0],
        piece,
        "P3",
        (mallet_instrument_type, "Red yarn:2"),
        (sticks, CHECKED_NOTES),
        (percussion, triangle),
    )
    _assign(
        db,
        users[1],
        piece,
        "P5",
        (mallet_instrument_type, "Red yarn:1"),
        (sticks, CHECKED_NOTES),
        (percussion, triangle),
    )
    # Already placed on Ode to Joy, so the later piece adds only Slap Stick.
    _assign(
        db,
        users[2],
        later,
        "P9",
        (mallet_instrument_type, "Red yarn:3"),
        (sticks, CHECKED_NOTES),
        (percussion, f"{triangle},{slap}"),
    )

    assert _placement(program) == [
        (
            "P3 - G4/A4",
            [
                ("Mallets", ["Red yarn\u00a0×2"]),
                ("Percussion", ["Triangle"]),
                ("Singing Bell Sticks", []),
            ],
        ),
        ("P5 - D5/E5", [("Mallets", ["Red yarn\u00a0×1"]), ("Singing Bell Sticks", [])]),
        ("P9 - E6/F6", [("Percussion", ["Slap Stick"])]),
    ]


def test_starting_placement_lists_other_spots_after_p11(
    db, program, piece, instrument_type
):
    users = [_ringer(db, f"Ringer {n}") for n in range(4)]
    db.session.commit()
    _assign(db, users[0], piece, "Float", (instrument_type, "C4"))
    _assign(db, users[1], piece, "LB2", (instrument_type, "D4"))
    _assign(db, users[2], piece, "P11", (instrument_type, "E4"))
    _assign(db, users[3], piece, "Other", (instrument_type, "F4"))

    assert [label for label, _ in _placement(program)] == [
        "P11 - B6/C7",
        "LB2",
        "Other",
        "Float",
    ]


def test_starting_placement_ignores_instruments_removed_from_the_piece(
    db, ringer, program, piece, instrument_type
):
    _assign(db, ringer, piece, "P1", (instrument_type, "C4"))
    piece.instrument_types.remove(instrument_type)
    db.session.commit()

    assert reports.starting_placement(program) == []


def test_starting_placement_page_only_for_programs_that_have_it(
    client, db, ringer, program, piece, instrument_type
):
    _assign(db, ringer, piece, "P1", (instrument_type, "C4,D4"))
    url = f"/programs/{program.id}/reports/starting-placement"
    login(client, ringer, RINGER_PASSWORD)

    assert url not in client.get("/").get_data(as_text=True)
    assert client.get(url).status_code == 404

    program.starting_placement = True
    db.session.commit()
    home = client.get("/").get_data(as_text=True)
    assert url in home
    assert home.index(url) < home.index("reports/equipment-table")
    body = client.get(url).get_data(as_text=True)
    assert "<h1>Starting Placement</h1>" in body
    assert "<h5>P1 - C4/D4</h5>" in body
    assert "<strong>Chimes:</strong> C4, D4" in body


def test_admin_turns_on_starting_placement(client, db, admin_user, cycle, program):
    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/admin/program/edit/?id={program.id}"
    assert "Starting placement report" in client.get(url).get_data(as_text=True)

    client.post(
        url,
        data={
            "cycle": cycle.id,
            "name": program.name,
            "datetime": "",
            "starting_placement": "y",
        },
    )
    db.session.expire_all()
    assert program.starting_placement is True


# --- coming from (cover sheets, starting placement programs) -------------


def _rows(program):
    """{(piece title, position): [(source, [(type name, items)])]} from the
    cover sheets."""
    return {
        (pp.piece.title, entry.position): [
            (source, [(t.name, items) for t, items in types])
            for source, types in coming_from
        ]
        for pp, ringers, _ in reports.cover_sheets(program)
        for entry, coming_from in ringers
    }


def _three_pieces(db, program, piece):
    second = add_piece(db, program, "Second", 2)
    third = add_piece(db, program, "Third", 3)
    program.starting_placement = True
    db.session.commit()
    return piece, second, third


def test_cover_sheets_show_where_a_moved_bell_is_coming_from(
    db, program, piece, instrument_type
):
    first, second, third = _three_pieces(db, program, piece)
    users = [_ringer(db, f"Ringer {n}") for n in range(6)]
    db.session.commit()
    _assign(db, users[0], first, "P4", (instrument_type, "C5,D5"))
    _assign(db, users[1], second, "P5", (instrument_type, "C5"))
    _assign(db, users[2], second, "P4", (instrument_type, "D5"))
    # Back to P4 for the third piece: C5 is now at P5.
    _assign(db, users[3], third, "P4", (instrument_type, "C5,D5"))

    rows = _rows(program)
    assert rows[("Ode to Joy", "P4")] == []
    assert rows[("Second", "P5")] == [("P4", [("Chimes", ["C5"])])]
    assert rows[("Second", "P4")] == []
    assert rows[("Third", "P4")] == [("P5", [("Chimes", ["C5"])])]


def test_cover_sheets_coming_from_ties_trees_percussion_and_lb(
    db, program, piece, instrument_type, mallet_instrument_type
):
    first, second, third = _three_pieces(db, program, piece)
    tree = _type(
        db, "Bell Tree", note_range_low="C5", note_range_high="C8", keyboard_type=True
    )
    percussion = _type(db, "Percussion", selection_mode="options")
    percussion.options = [InstrumentOption(name="Triangle")]
    db.session.commit()
    triangle = str(percussion.options[0].id)
    users = [_ringer(db, f"Ringer {n}") for n in range(6)]
    db.session.commit()
    # Same piece, same chime: P3 starts with it, so P5 takes it from P3.
    _assign(db, users[0], first, "P3", (instrument_type, "C5"), (tree, "E5"))
    _assign(
        db,
        users[1],
        first,
        "P5",
        (instrument_type, "C5"),
        (mallet_instrument_type, "Red yarn:1"),
    )
    _assign(db, users[2], first, "LB1", (percussion, triangle))
    # The tree moves whole: P7 uses other pitches on it.
    _assign(
        db,
        users[3],
        second,
        "P7",
        (tree, "C6,G5"),
        (percussion, triangle),
        (mallet_instrument_type, "Red yarn:1"),
    )

    rows = _rows(program)
    assert rows[("Ode to Joy", "P3")] == []
    assert rows[("Ode to Joy", "P5")] == [("P3", [("Chimes", ["C5"])])]
    assert rows[("Second", "P7")] == [
        ("P3", [("Bell Tree", ["G5", "C6"])]),
        ("LB1", [("Percussion", ["Triangle"])]),
    ]


def test_cover_sheets_have_no_coming_from_without_starting_placement(
    client, db, admin_user, program, piece, instrument_type
):
    second = add_piece(db, program, "Second", 2)
    db.session.commit()
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(db, users[0], piece, "P4", (instrument_type, "C5"))
    _assign(db, users[1], second, "P5", (instrument_type, "C5"))

    assert all(coming == [] for coming in _rows(program).values())
    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/programs/{program.id}/reports/cover-sheets"
    assert "Coming from P4:" not in client.get(url).get_data(as_text=True)

    program.starting_placement = True
    db.session.commit()
    body = client.get(url).get_data(as_text=True)
    assert "Coming from P4:" in body
    assert "<strong>Chimes:</strong> C5" in body


def test_bass_cover_sheets_start_placed_bells_at_their_position(
    db, program, piece, instrument_type, bass_instrument_type
):
    program.starting_placement = True
    low = _ringer(db, "Low One")
    db.session.commit()
    lb1 = _assign(
        db, low, piece, "LB1",
        (bass_instrument_type, "C3"), (instrument_type, "C4"),
    )

    [(_, [(entry, _, sources, _)])] = reports.bass_bell_cover_sheets(program)
    assert entry == lb1
    assert sources == [
        ("Already here", [(instrument_type, ["C4"])]),
        ("Coming from Floor", [(bass_instrument_type, ["C3"])]),
    ]
