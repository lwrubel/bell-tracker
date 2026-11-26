from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login
from test_reports import _assign, _ringer, _type

from app import reports
from app.models import (
    CHECKED_NOTES,
    InstrumentOption,
    Program,
    ProgramEarlyPutOut,
    ProgramKeepOut,
)


def _sets(db, program, *set_numbers):
    """Pieces "Piece 1", "Piece 2", ... in program order, numbered into sets."""
    pieces = [
        add_piece(db, program, f"Piece {i}", i) for i in range(1, len(set_numbers) + 1)
    ]
    db.session.flush()
    for program_piece, number in zip(program.program_pieces, set_numbers):
        program_piece.set_number = number
    db.session.commit()
    return pieces


def _flat(positions):
    return [
        (position, [(t.name, items) for t, items in types])
        for position, types in positions
    ]


def _resets(program):
    """resets with types flattened to names."""
    return [
        (r.title, _flat(r.take_off), _flat(r.put_out))
        for r in reports.resets(program)
    ]


# --- sets ----------------------------------------------------------------


def test_program_without_set_numbers_has_no_sets(db, program, piece):
    assert not program.has_sets
    assert program.sets() == []
    assert reports.resets(program) == []


def test_sets_group_program_pieces_in_order(db, program):
    _sets(db, program, 1, 1, 2, 3, 3)

    assert program.has_sets
    assert [[pp.piece.title for pp in s] for s in program.sets()] == [
        ["Piece 1", "Piece 2"],
        ["Piece 3"],
        ["Piece 4", "Piece 5"],
    ]


def _post_program(client, program, rows):
    data = {"cycle": program.cycle_id, "name": program.name}
    for i, (program_piece, set_number) in enumerate(rows):
        data[f"program_pieces-{i}-id"] = program_piece.id
        data[f"program_pieces-{i}-piece"] = program_piece.piece_id
        data[f"program_pieces-{i}-position"] = program_piece.position
        data[f"program_pieces-{i}-set_number"] = set_number
    return client.post(
        f"/admin/program/edit/?id={program.id}", data=data, follow_redirects=True
    ).get_data(as_text=True)


def test_admin_unticks_cover_sheet(client, db, admin_user, program):
    _sets(db, program, None, None)
    first, second = program.program_pieces
    login(client, admin_user, ADMIN_PASSWORD)

    form = client.get(f"/admin/program/edit/?id={program.id}").get_data(as_text=True)
    assert "Cover sheet" in form
    data = {"cycle": program.cycle_id, "name": program.name}
    for i, program_piece in enumerate([first, second]):
        data[f"program_pieces-{i}-id"] = program_piece.id
        data[f"program_pieces-{i}-piece"] = program_piece.piece_id
        data[f"program_pieces-{i}-position"] = program_piece.position
        data[f"program_pieces-{i}-set_number"] = ""
    data["program_pieces-0-cover_sheet"] = "y"  # the second is left unticked
    client.post(f"/admin/program/edit/?id={program.id}", data=data)

    db.session.expire_all()
    program = db.session.get(Program, program.id)
    assert [pp.cover_sheet for pp in program.program_pieces] == [True, False]


def test_admin_sets_set_numbers(client, db, admin_user, program):
    _sets(db, program, None, None)
    first, second = program.program_pieces
    login(client, admin_user, ADMIN_PASSWORD)

    assert "Set" in client.get(f"/admin/program/edit/?id={program.id}").get_data(
        as_text=True
    )
    _post_program(client, program, [(first, 1), (second, 2)])

    db.session.expire_all()
    program = db.session.get(Program, program.id)
    assert [pp.set_number for pp in program.program_pieces] == [1, 2]


def test_admin_rejects_set_numbers_on_only_some_pieces(
    client, db, admin_user, program
):
    _sets(db, program, None, None)
    first, second = program.program_pieces
    login(client, admin_user, ADMIN_PASSWORD)

    body = _post_program(client, program, [(first, 1), (second, "")])

    assert "Give every piece a set number" in body
    db.session.expire_all()
    assert not db.session.get(Program, program.id).has_sets


def test_admin_rejects_set_numbers_going_down(client, db, admin_user, program):
    _sets(db, program, None, None)
    first, second = program.program_pieces
    login(client, admin_user, ADMIN_PASSWORD)

    body = _post_program(client, program, [(first, 2), (second, 1)])

    assert "Set numbers must not go down" in body


# --- resets --------------------------------------------------------------


def test_before_set_1_puts_items_where_first_used_in_the_set(
    db, program, instrument_type, bass_instrument_type
):
    main = _type(db, "Main Bells", note_range_low="C4", note_range_high="C8")
    bass_chimes = _type(
        db, "Bass Chimes", note_range_low="C2", note_range_high="B3", display_order=15
    )
    one, two = _sets(db, program, 1, 1)
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    db.session.commit()
    _assign(db, users[0], one, "P5", (main, "C5"), (instrument_type, "D5,C5"))
    _assign(db, users[1], two, "P8", (instrument_type, "C5,C6"))
    _assign(
        db, users[2], one, "LB1", (bass_instrument_type, "C3"), (bass_chimes, "A2")
    )

    assert _resets(program) == [
        (
            "Before Set 1",
            [],
            [
                ("P5", [("Chimes", ["C5", "D5"])]),
                ("P8", [("Chimes", ["C6"])]),
                ("LB1", [("Bass Bells", ["C3"]), ("Bass Chimes", ["A2"])]),
            ],
        )
    ]


def test_reset_takes_off_what_the_next_set_skips_and_puts_out_whats_new(
    db, program, instrument_type
):
    one, two, three = _sets(db, program, 1, 1, 2)
    users = [_ringer(db, f"Ringer {n}") for n in range(3)]
    db.session.commit()
    # C5 and D5 start at P5; P7 rings D5 last in Set 1, so P7 takes it off.
    _assign(db, users[0], one, "P5", (instrument_type, "C5,D5"))
    _assign(db, users[1], two, "P7", (instrument_type, "D5"))
    # Set 2 still uses C5 (stays out) and adds E5 at P3.
    _assign(db, users[2], three, "P3", (instrument_type, "C5,E5"))

    assert _resets(program)[1] == (
        "Reset between Sets 1 and 2",
        [("P7", [("Chimes", ["D5"])])],
        [("P3", [("Chimes", ["E5"])])],
    )


def test_no_reset_after_the_last_set(db, program, instrument_type):
    one, two = _sets(db, program, 1, 2)
    user = _ringer(db, "Ringer")
    db.session.commit()
    _assign(db, user, one, "P1", (instrument_type, "C4"))
    _assign(db, user, two, "P1", (instrument_type, "D4"))

    assert [title for title, _, _ in _resets(program)] == [
        "Before Set 1",
        "Reset between Sets 1 and 2",
    ]


def test_bell_tree_moves_as_one_item(db, program):
    tree = _type(
        db, "Bell Tree", note_range_low="C5", note_range_high="C8", keyboard_type=True
    )
    one, two, three = _sets(db, program, 1, 1, 2)
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(db, users[0], one, "P7", (tree, "E5"))
    _assign(db, users[1], two, "P3", (tree, "C5,G6"))
    _assign(db, users[0], three, "P1", (tree, "C5"))

    before, reset = _resets(program)
    assert before[2] == [("P7", [("Bell Tree", ["C5", "E5", "G6"])])]
    # Set 2 uses the tree too, so it stays out.
    assert reset[1:] == ([], [])


def test_mallets_sticks_and_percussion(db, program, mallet_instrument_type):
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
    one, two, three = _sets(db, program, 1, 1, 2)
    users = [_ringer(db, f"Ringer {n}") for n in range(2)]
    db.session.commit()
    _assign(
        db,
        users[0],
        one,
        "P3",
        (mallet_instrument_type, "Red yarn:1"),
        (sticks, CHECKED_NOTES),
        (percussion, ids["Triangle"]),
    )
    _assign(db, users[0], two, "P3", (mallet_instrument_type, "Red yarn:3"))
    _assign(
        db,
        users[1],
        three,
        "P3",
        (mallet_instrument_type, "Red yarn:1"),
        (percussion, ids["Slap Stick"]),
    )

    before, reset = _resets(program)
    assert before[2] == [
        (
            "P3",
            [
                ("Mallets", ["Red yarn ×3"]),
                ("Percussion", ["Triangle"]),
                ("Singing Bell Sticks", []),
            ],
        )
    ]
    assert reset[1:] == (
        [
            (
                "P3",
                [
                    ("Mallets", ["Red yarn ×2"]),
                    ("Percussion", ["Triangle"]),
                    ("Singing Bell Sticks", []),
                ],
            )
        ],
        [("P3", [("Percussion", ["Slap Stick"])])],
    )


def _names(types):
    return [(t.name, items) for t, items in types]


def _single(rows):
    """my_resets rows for a ringer with at most one position per piece, as
    (reset, end position, take off, leave on, start position, put out)."""
    result = []
    for reset, ends, starts, _, _ in rows:
        assert len(ends) <= 1 and len(starts) <= 1
        end, off, leave = ends[0] if ends else (None, [], [])
        start, out = starts[0] if starts else (None, [])
        result.append((reset, end, off, leave, start, out))
    return result


def _mine(program, user):
    return [
        (r.title, end, _names(off), start, _names(out))
        for r, end, off, _, start, out in _single(reports.my_resets(program, user))
    ]


def test_my_resets_use_start_and_end_positions_across_a_reset(
    db, program, instrument_type
):
    one, two, three, four = _sets(db, program, 1, 1, 2, 2)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    # I start Set 1 at P1, end it at P5, and come back for Set 2 at P2.
    _assign(db, me, one, "P1", (instrument_type, "C4"))
    _assign(db, me, two, "P5", (instrument_type, "D5"))
    _assign(db, me, three, "P2", (instrument_type, "E4"))
    _assign(db, me, four, "P8", (instrument_type, "C6"))
    # Someone else starts Set 1 at P5 and puts out D5 for me, but isn't on
    # the set's last piece, so I take it off, not them.
    _assign(db, other, one, "P5", (instrument_type, "D5"))

    assert _mine(program, me) == [
        ("Before Set 1", None, [], "P1", [("Chimes", ["C4"])]),
        ("Reset between Sets 1 and 2", "P5", [("Chimes", ["D5"])], "P2", [("Chimes", ["E4"])]),
    ]
    assert _mine(program, other) == [
        ("Before Set 1", None, [], "P5", [("Chimes", ["D5"])]),
        ("Reset between Sets 1 and 2", None, [], None, []),
    ]


def test_my_resets_put_out_nothing_when_not_on_the_sets_first_piece(
    db, program, instrument_type
):
    one, two, three, four = _sets(db, program, 1, 1, 2, 2)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    # Someone else at P4 on the first piece puts C5 out; I only join on
    # the second piece, at P4 too.
    _assign(db, other, one, "P4", (instrument_type, "C5"))
    _assign(db, me, two, "P4", (instrument_type, "C5"))
    # I sit out Set 2's first piece, then ring D5 on its last.
    _assign(db, other, three, "P6", (instrument_type, "D5"))
    _assign(db, me, four, "P6", (instrument_type, "D5"))

    assert _mine(program, me) == [
        ("Before Set 1", None, [], None, []),
        ("Reset between Sets 1 and 2", "P4", [("Chimes", ["C5"])], None, []),
    ]
    # The other ringer sat out Set 1's last piece, so takes nothing off.
    assert _mine(program, other)[1][1:] == (None, [], "P6", [("Chimes", ["D5"])])


def test_my_resets_page_when_not_on_a_sets_first_piece(
    client, db, ringer, program, instrument_type
):
    one, two = _sets(db, program, 1, 1)
    _assign(db, ringer, two, "P4", (instrument_type, "C5"))
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    assert "You haven't been assigned" not in body
    assert "you aren't on Piece 1, the first piece of Set 1" in body


def test_my_resets_page_when_not_on_a_sets_last_piece(
    client, db, ringer, program, instrument_type
):
    one, two, three = _sets(db, program, 1, 1, 2)
    _assign(db, ringer, one, "P4", (instrument_type, "C5"))
    _assign(db, ringer, three, "P4", (instrument_type, "D5"))
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    assert "you aren't on Piece 2, the last piece of Set 1" in body


def test_my_resets_cover_each_position_on_a_sets_first_and_last_piece(
    db, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, one, "P1", (instrument_type, "C4"))
    _assign(db, me, two, "P2", (instrument_type, "E4"))
    _assign(db, me, two, "P8", (instrument_type, "C6"))

    (_, before_ends, before_starts, _, _), (_, ends, starts, _, _) = reports.my_resets(
        program, me
    )
    assert before_ends == []
    assert [(p, _names(out)) for p, out in before_starts] == [
        ("P1", [("Chimes", ["C4"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]
    assert [(p, _names(off)) for p, off, _ in ends] == [
        ("P1", [("Chimes", ["C4"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]
    assert [(p, _names(out)) for p, out in starts] == [
        ("P2", [("Chimes", ["E4"])]),
        ("P8", [("Chimes", ["C6"])]),
    ]


def test_my_resets_page_shows_each_position(
    client, db, ringer, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    _assign(db, ringer, one, "P1", (instrument_type, "C4"))
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, two, "P2", (instrument_type, "E4"))
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    reset = body[body.index("Reset between Sets 1 and 2"):]
    assert "You end Set 1 at P1 - C4/D4 on Piece 1" in reset
    assert "You end Set 1 at P5 - D5/E5 on Piece 1" in reset
    assert "You start Set 2 at P2 - E4/F4 on Piece 2" in reset


# --- pages ---------------------------------------------------------------


def test_reset_pages_404_without_sets(client, db, admin_user, program, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    home = client.get("/").get_data(as_text=True)

    assert "my-resets" not in home
    assert "reports/resets" not in home
    assert client.get(f"/programs/{program.id}/my-resets").status_code == 404
    assert client.get(f"/programs/{program.id}/reports/resets").status_code == 404


def test_my_resets_page(client, db, ringer, program, instrument_type):
    one, two = _sets(db, program, 1, 2)
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, two, "P2", (instrument_type, "E4"))
    login(client, ringer, RINGER_PASSWORD)

    home = client.get("/").get_data(as_text=True)
    assert f"/programs/{program.id}/my-resets" in home
    assert "reports/resets" not in home
    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    assert "Reset between Sets 1 and 2" in body
    assert "You end Set 1 at P5 - D5/E5 on Piece 1" in body
    assert "You start Set 2 at P2 - E4/F4 on Piece 2" in body
    assert "<strong>Chimes:</strong> E4" in body
    assert 'id="print-date-footer"' in body
    assert client.get(f"/programs/{program.id}/reports/resets").status_code == 403


def test_my_resets_page_for_someone_not_in_the_program(
    client, db, admin_user, program
):
    _sets(db, program, 1, 2)
    login(client, admin_user, ADMIN_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    assert "You haven't been assigned" in body


def test_resets_report_page(client, db, manager, ringer, program, instrument_type):
    one, two = _sets(db, program, 1, 2)
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, two, "P2", (instrument_type, "E4"))
    login(client, manager, RINGER_PASSWORD)

    assert f"/programs/{program.id}/reports/resets" in client.get("/").get_data(
        as_text=True
    )
    body = client.get(f"/programs/{program.id}/reports/resets").get_data(as_text=True)
    assert "<h2>Before Set 1</h2>" in body
    assert "<h2>Reset between Sets 1 and 2</h2>" in body
    assert "<h5>P5 - D5/E5</h5>" in body
    assert "<em>Take off</em>" in body


def test_program_order_shows_set_headings(client, db, ringer, program):
    _sets(db, program, 1, 2)
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/order").get_data(as_text=True)
    assert body.index("Set 1") < body.index("Piece 1") < body.index("Set 2")


def test_everyones_resets_gives_each_ringer_their_own_rows(
    db, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    zoe, amy = _ringer(db, "Zoe"), _ringer(db, "Amy")
    db.session.commit()
    _assign(db, zoe, one, "P5", (instrument_type, "D5"))
    _assign(db, amy, two, "P2", (instrument_type, "E4"))

    ringers = reports.everyones_resets(program)
    assert [user.name for user, _ in ringers] == ["Amy", "Zoe"]
    (_, amy_rows), (_, zoe_rows) = ringers
    assert [(end, start) for _, end, _, _, start, _ in _single(amy_rows)] == [
        (None, None),
        (None, "P2"),
    ]
    assert [(end, start) for _, end, _, _, start, _ in _single(zoe_rows)] == [
        (None, "P5"),
        ("P5", None),
    ]


def test_everyones_resets_page(client, db, manager, ringer, program, instrument_type):
    one, two = _sets(db, program, 1, 2)
    other = _ringer(db, "Zed Ringer")
    db.session.commit()
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, other, two, "P2", (instrument_type, "E4"))
    url = f"/programs/{program.id}/reports/everyones-resets"

    login(client, ringer, RINGER_PASSWORD)
    assert url not in client.get("/").get_data(as_text=True)
    assert client.get(url).status_code == 403
    client.post("/logout")

    login(client, manager, RINGER_PASSWORD)
    assert url in client.get("/").get_data(as_text=True)
    body = client.get(url).get_data(as_text=True)
    assert body.count('<section class="ringer-resets">') == 2
    assert body.index("<h1>Ringer One</h1>") < body.index("<h1>Zed Ringer</h1>")
    # No "My resets · program" line under each name, to save space.
    assert "My resets &middot;" not in body
    assert 'id="print-date-footer"' in body
    assert "You start Set 2 at P2 - E4/F4 on Piece 2" in body


def test_everyones_resets_404_without_sets(client, db, admin_user, program, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/programs/{program.id}/reports/everyones-resets"
    assert client.get(url).status_code == 404


# --- leave on table --------------------------------------------------------


def _keep_out(db, program, instrument_type, after_set):
    db.session.add(
        ProgramKeepOut(
            program_id=program.id,
            instrument_type_id=instrument_type.id,
            after_set=after_set,
        )
    )
    db.session.commit()
    db.session.refresh(program)


def _leave_on(program):
    return [(r.title, _flat(r.leave_on)) for r in reports.resets(program)]


def test_keep_out_leaves_a_type_on_the_table_for_one_more_set(
    db, program, instrument_type
):
    handbells = _type(db, "Handbells", note_range_low="C4", note_range_high="C8")
    one, two, three = _sets(db, program, 1, 2, 3)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"), (handbells, "C6"))
    _assign(db, other, two, "P2", (handbells, "E5"))
    _assign(db, other, three, "P2", (handbells, "E5"))
    _keep_out(db, program, instrument_type, 1)

    assert _resets(program)[1:] == [
        (
            "Reset between Sets 1 and 2",
            # Chimes stay; Handbells weren't kept, so they come off as usual.
            [("P5", [("Handbells", ["C6"])])],
            [("P2", [("Handbells", ["E5"])])],
        ),
        (
            "Reset between Sets 2 and 3",
            # The position that left them on takes them off a Reset later.
            [("P5", [("Chimes", ["D5"])])],
            [],
        ),
    ]
    assert _leave_on(program) == [
        ("Before Set 1", []),
        ("Reset between Sets 1 and 2", [("P5", [("Chimes", ["D5"])])]),
        ("Reset between Sets 2 and 3", []),
    ]


def test_keep_out_only_leaves_on_what_the_next_set_doesnt_use(
    db, program, instrument_type
):
    one, two, three = _sets(db, program, 1, 2, 3)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5,E5"))
    _assign(db, other, two, "P2", (instrument_type, "E5"))
    _keep_out(db, program, instrument_type, 1)

    assert _leave_on(program)[1] == (
        "Reset between Sets 1 and 2",
        [("P5", [("Chimes", ["D5"])])],
    )
    # E5 moves to P2 in Set 2, so P2 takes it off; D5 stayed at P5.
    assert _resets(program)[2][1] == [
        ("P2", [("Chimes", ["E5"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]


def test_keep_outs_in_a_row_leave_a_type_out_for_two_more_sets(
    db, program, instrument_type
):
    one, two, three, four = _sets(db, program, 1, 2, 3, 4)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, other, two, "P2", (instrument_type, "C4"))
    _keep_out(db, program, instrument_type, 1)
    _keep_out(db, program, instrument_type, 2)

    assert _leave_on(program)[1:] == [
        ("Reset between Sets 1 and 2", [("P5", [("Chimes", ["D5"])])]),
        (
            "Reset between Sets 2 and 3",
            [("P2", [("Chimes", ["C4"])]), ("P5", [("Chimes", ["D5"])])],
        ),
        ("Reset between Sets 3 and 4", []),
    ]
    assert _resets(program)[3][1] == [
        ("P2", [("Chimes", ["C4"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]


def test_my_resets_page_shows_leave_on_table(
    client, db, ringer, manager, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, two, "P5", (instrument_type, "E4"))
    _keep_out(db, program, instrument_type, 1)
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    reset = body[body.index("Reset between Sets 1 and 2"):]
    assert "Leave on table" in reset
    assert "Stays out for Set 2</span>" in reset
    assert "<strong>Chimes:</strong> D5" in reset
    assert "Nothing to take off." not in reset
    client.post("/logout")

    login(client, manager, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/reports/resets").get_data(as_text=True)
    assert "Leave on table for Set 2" in body


def _post_keep_out(client, program, instrument_type, after_set):
    data = {"cycle": program.cycle_id, "name": program.name}
    for i, program_piece in enumerate(program.program_pieces):
        data[f"program_pieces-{i}-id"] = program_piece.id
        data[f"program_pieces-{i}-piece"] = program_piece.piece_id
        data[f"program_pieces-{i}-position"] = program_piece.position
        data[f"program_pieces-{i}-set_number"] = program_piece.set_number or ""
    data["keep_outs-0-instrument_type"] = instrument_type.id
    data["keep_outs-0-after_set"] = after_set
    return client.post(
        f"/admin/program/edit/?id={program.id}", data=data, follow_redirects=True
    ).get_data(as_text=True)


def test_admin_adds_a_keep_out(client, db, admin_user, program, instrument_type):
    _sets(db, program, 1, 2)
    login(client, admin_user, ADMIN_PASSWORD)

    assert "Leave on table" in client.get(
        f"/admin/program/edit/?id={program.id}"
    ).get_data(as_text=True)
    _post_keep_out(client, program, instrument_type, 1)

    db.session.expire_all()
    program = db.session.get(Program, program.id)
    assert [(k.instrument_type.name, k.after_set) for k in program.keep_outs] == [
        ("Chimes", 1)
    ]


def test_admin_rejects_keep_out_after_the_last_set(
    client, db, admin_user, program, instrument_type
):
    _sets(db, program, 1, 2)
    login(client, admin_user, ADMIN_PASSWORD)

    assert "Set 2 is the last set" in _post_keep_out(client, program, instrument_type, 2)
    assert "this program has no Set 5" in _post_keep_out(
        client, program, instrument_type, 5
    )
    db.session.expire_all()
    assert db.session.get(Program, program.id).keep_outs == []


# --- put out early ---------------------------------------------------------


def _early(db, program, instrument_type, before_set):
    db.session.add(
        ProgramEarlyPutOut(
            program_id=program.id,
            instrument_type_id=instrument_type.id,
            before_set=before_set,
        )
    )
    db.session.commit()
    db.session.refresh(program)


def test_put_out_early_puts_out_the_next_sets_items_before_this_set(
    db, program, instrument_type
):
    handbells = _type(db, "Handbells", note_range_low="C4", note_range_high="C8")
    one, two, three = _sets(db, program, 1, 2, 3)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    # Set 2 needs E4 chimes at P2, and handbells that aren't put out early.
    _assign(db, other, two, "P2", (instrument_type, "E4"), (handbells, "E5"))
    _early(db, program, instrument_type, 1)

    assert _resets(program) == [
        (
            "Before Set 1",
            [],
            [("P2", [("Chimes", ["E4"])]), ("P5", [("Chimes", ["D5"])])],
        ),
        (
            "Reset between Sets 1 and 2",
            # D5 comes off as usual; E4 is already out at P2.
            [("P5", [("Chimes", ["D5"])])],
            [("P2", [("Handbells", ["E5"])])],
        ),
        (
            "Reset between Sets 2 and 3",
            [("P2", [("Chimes", ["E4"]), ("Handbells", ["E5"])])],
            [],
        ),
    ]


def test_put_out_early_skips_what_this_set_already_puts_out(
    db, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, other, two, "P2", (instrument_type, "D5,E4"))
    _early(db, program, instrument_type, 1)

    before, between = _resets(program)
    # D5 goes out once, where Set 1 first uses it.
    assert before[2] == [("P2", [("Chimes", ["E4"])]), ("P5", [("Chimes", ["D5"])])]
    assert between[1:] == ([], [])


def test_put_outs_early_in_a_row_reach_two_sets_ahead(db, program, instrument_type):
    one, two, three = _sets(db, program, 1, 2, 3)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, two, "P5", (instrument_type, "D5"))
    _assign(db, me, three, "P2", (instrument_type, "E4"))
    _early(db, program, instrument_type, 1)
    _early(db, program, instrument_type, 2)

    assert _resets(program)[0][2] == [
        ("P2", [("Chimes", ["E4"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]
    between_1_2, between_2_3 = _resets(program)[1:]
    assert between_1_2[1:] == ([], [])
    # D5 comes off after Set 2, the last to use it; E4 is already out.
    assert between_2_3[1:] == ([("P5", [("Chimes", ["D5"])])], [])


def test_put_out_early_with_leave_on_table_keeps_both_sets_items_out(
    db, program, instrument_type
):
    handbells = _type(db, "Handbells", note_range_low="C4", note_range_high="C8")
    one, two, three = _sets(db, program, 1, 2, 3)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, other, two, "P2", (instrument_type, "E4"))
    _assign(db, other, three, "P2", (handbells, "E5"))
    _early(db, program, instrument_type, 1)
    _keep_out(db, program, instrument_type, 1)

    before, between_1_2, between_2_3 = _resets(program)
    assert before[2] == [("P2", [("Chimes", ["E4"])]), ("P5", [("Chimes", ["D5"])])]
    assert between_1_2[1:] == ([], [])
    assert _leave_on(program)[1][1] == [("P5", [("Chimes", ["D5"])])]
    assert between_2_3[1] == [
        ("P2", [("Chimes", ["E4"])]),
        ("P5", [("Chimes", ["D5"])]),
    ]


def test_my_resets_put_out_early_items_at_their_position(
    db, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P2", (instrument_type, "C4"))
    _assign(db, me, two, "P2", (instrument_type, "E4"))
    _early(db, program, instrument_type, 1)

    assert _mine(program, me) == [
        ("Before Set 1", None, [], "P2", [("Chimes", ["C4", "E4"])]),
        ("Reset between Sets 1 and 2", "P2", [("Chimes", ["C4"])], "P2", []),
    ]


def _post_early(client, program, instrument_type, before_set):
    data = {"cycle": program.cycle_id, "name": program.name}
    for i, program_piece in enumerate(program.program_pieces):
        data[f"program_pieces-{i}-id"] = program_piece.id
        data[f"program_pieces-{i}-piece"] = program_piece.piece_id
        data[f"program_pieces-{i}-position"] = program_piece.position
        data[f"program_pieces-{i}-set_number"] = program_piece.set_number or ""
    data["early_put_outs-0-instrument_type"] = instrument_type.id
    data["early_put_outs-0-before_set"] = before_set
    return client.post(
        f"/admin/program/edit/?id={program.id}", data=data, follow_redirects=True
    ).get_data(as_text=True)


def test_admin_adds_an_early_put_out(client, db, admin_user, program, instrument_type):
    _sets(db, program, 1, 2)
    login(client, admin_user, ADMIN_PASSWORD)

    assert "Put out early" in client.get(
        f"/admin/program/edit/?id={program.id}"
    ).get_data(as_text=True)
    _post_early(client, program, instrument_type, 1)

    db.session.expire_all()
    program = db.session.get(Program, program.id)
    assert [
        (e.instrument_type.name, e.before_set) for e in program.early_put_outs
    ] == [("Chimes", 1)]


def test_admin_rejects_early_put_out_before_the_last_set(
    client, db, admin_user, program, instrument_type
):
    _sets(db, program, 1, 2)
    login(client, admin_user, ADMIN_PASSWORD)

    body = _post_early(client, program, instrument_type, 2)
    assert "put things out early before Set 2: Set 2 is the last set" in body
    db.session.expire_all()
    assert db.session.get(Program, program.id).early_put_outs == []


# --- non-handbell pieces ---------------------------------------------------


def _non_handbell(db, program, *pieces):
    ids = {p.id for p in pieces}
    for program_piece in program.program_pieces:
        if program_piece.piece_id in ids:
            program_piece.non_handbell = True
    db.session.commit()


def test_non_handbell_first_piece_doesnt_decide_who_puts_out(
    db, program, instrument_type
):
    choir, one, two = _sets(db, program, 1, 1, 2)
    me, other = _ringer(db, "Me"), _ringer(db, "Other")
    db.session.commit()
    # Someone is down at P2 on the choir piece, but I start the handbells.
    _assign(db, other, choir, "P2", (instrument_type, "E4"))
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, two, "P5", (instrument_type, "D5"))
    _non_handbell(db, program, choir)

    before = reports.resets(program)[0]
    assert before.started_piece == one
    assert _flat(before.put_out) == [("P5", [("Chimes", ["D5"])])]
    assert _mine(program, me)[0] == (
        "Before Set 1", None, [], "P5", [("Chimes", ["D5"])]
    )
    assert _mine(program, other)[0] == ("Before Set 1", None, [], None, [])


def test_non_handbell_last_piece_doesnt_decide_who_takes_off(
    client, db, ringer, program, instrument_type
):
    one, choir, two = _sets(db, program, 1, 1, 2)
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, two, "P2", (instrument_type, "E4"))
    _non_handbell(db, program, choir)

    reset = reports.resets(program)[1]
    assert reset.ended_piece == one
    assert _flat(reset.take_off) == [("P5", [("Chimes", ["D5"])])]
    assert _mine(program, ringer)[1][1:3] == ("P5", [("Chimes", ["D5"])])

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    assert "You end Set 1 at P5 - D5/E5 on Piece 1" in body


def test_set_of_only_non_handbell_pieces_is_skipped(db, program, instrument_type):
    one, choir, three = _sets(db, program, 1, 2, 3)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, three, "P5", (instrument_type, "D5,E5"))
    _non_handbell(db, program, choir)

    assert _resets(program) == [
        ("Before Set 1", [], [("P5", [("Chimes", ["D5"])])]),
        ("Reset between Sets 1 and 3", [], [("P5", [("Chimes", ["E5"])])]),
    ]


def test_program_order_marks_non_handbell_pieces(client, db, ringer, program):
    one, choir = _sets(db, program, 1, 1)
    _non_handbell(db, program, choir)
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/order").get_data(as_text=True)
    assert body.count("(non-handbell)") == 1
    assert body.index("Piece 2") < body.index("(non-handbell)")


def test_admin_ticks_non_handbell(client, db, admin_user, program):
    _sets(db, program, None, None)
    first, second = program.program_pieces
    login(client, admin_user, ADMIN_PASSWORD)

    form = client.get(f"/admin/program/edit/?id={program.id}").get_data(as_text=True)
    assert "Non-handbell" in form
    data = {"cycle": program.cycle_id, "name": program.name}
    for i, program_piece in enumerate([first, second]):
        data[f"program_pieces-{i}-id"] = program_piece.id
        data[f"program_pieces-{i}-piece"] = program_piece.piece_id
        data[f"program_pieces-{i}-position"] = program_piece.position
        data[f"program_pieces-{i}-set_number"] = ""
        data[f"program_pieces-{i}-cover_sheet"] = "y"
    data["program_pieces-1-non_handbell"] = "y"
    client.post(f"/admin/program/edit/?id={program.id}", data=data)

    db.session.expire_all()
    program = db.session.get(Program, program.id)
    assert [pp.non_handbell for pp in program.program_pieces] == [False, True]


# --- pieces between the reset cards ----------------------------------------


def _pieces(sets):
    return [
        (number, [(pp.piece.title, positions) for pp, positions in pieces])
        for number, pieces in sets
    ]


def test_my_resets_list_each_sets_pieces_with_my_positions(
    db, program, instrument_type
):
    one, two, three = _sets(db, program, 1, 1, 2)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, one, "P1", (instrument_type, "C4"))
    _assign(db, me, three, "P2", (instrument_type, "E4"))

    rows = reports.my_resets(program, me)
    assert [_pieces(row[3]) for row in rows] == [[], []]
    assert [_pieces(row[4]) for row in rows] == [
        [(1, [("Piece 1", ["P1", "P5"]), ("Piece 2", [])])],
        [(2, [("Piece 3", ["P2"])])],
    ]


def test_non_handbell_sets_are_listed_where_they_fall(db, program, instrument_type):
    choir, one, choir_two, three = _sets(db, program, 1, 2, 3, 4)
    me = _ringer(db, "Me")
    db.session.commit()
    _assign(db, me, one, "P5", (instrument_type, "D5"))
    _assign(db, me, three, "P5", (instrument_type, "D5"))
    _non_handbell(db, program, choir, choir_two)

    rows = reports.my_resets(program, me)
    assert [row[0].title for row in rows] == [
        "Before Set 2",
        "Reset between Sets 2 and 4",
    ]
    assert _pieces(rows[0][3]) == [(1, [("Piece 1", [])])]
    assert _pieces(rows[0][4]) == [
        (2, [("Piece 2", ["P5"])]),
        (3, [("Piece 3", [])]),
    ]
    assert _pieces(rows[1][3]) == []
    assert _pieces(rows[1][4]) == [(4, [("Piece 4", ["P5"])])]


def test_my_resets_page_shows_pieces_between_cards(
    client, db, ringer, program, instrument_type
):
    one, choir, two, three = _sets(db, program, 1, 1, 1, 2)
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, ringer, three, "P2", (instrument_type, "E4"))
    _non_handbell(db, program, choir)
    login(client, ringer, RINGER_PASSWORD)

    body = client.get(f"/programs/{program.id}/my-resets").get_data(as_text=True)
    first_card = body.index("Before Set 1")
    set_1 = body.index("<strong>Set 1</strong>")
    second_card = body.index("Reset between Sets 1 and 2")
    set_2 = body.index("<strong>Set 2</strong>")
    assert first_card < set_1 < second_card < set_2
    set_1_line = body[set_1:second_card]
    assert "1. Piece 1 (P5)" in set_1_line
    assert "2. Piece 2 (non-handbell)" in set_1_line
    assert "3. Piece 3 (\u2014)" in set_1_line
    assert "4. Piece 4 (P2)" in body[set_2:]


def test_everyones_resets_page_lists_each_ringers_own_positions(
    client, db, manager, ringer, program, instrument_type
):
    one, two = _sets(db, program, 1, 2)
    other = _ringer(db, "Zed Ringer")
    db.session.commit()
    _assign(db, ringer, one, "P5", (instrument_type, "D5"))
    _assign(db, other, one, "P2", (instrument_type, "E4"))
    login(client, manager, RINGER_PASSWORD)

    body = client.get(
        f"/programs/{program.id}/reports/everyones-resets"
    ).get_data(as_text=True)
    mine, theirs = body.split("<h1>Zed Ringer</h1>")
    assert "1. Piece 1 (P5)" in mine
    assert "1. Piece 1 (P2)" in theirs
    assert theirs.count("<strong>Set 2</strong>") == 1
