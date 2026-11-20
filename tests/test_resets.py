from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login
from test_reports import _assign, _ringer, _type

from app import reports
from app.models import CHECKED_NOTES, InstrumentOption, Program


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
        "Reset after Set 1",
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
        "Reset after Set 1",
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


def _mine(program, user):
    return [
        (r.title, end, [(t.name, i) for t, i in off], start, [(t.name, i) for t, i in out])
        for r, end, off, start, out in reports.my_resets(program, user)
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
        ("Reset after Set 1", "P5", [("Chimes", ["D5"])], "P2", [("Chimes", ["E4"])]),
    ]
    assert _mine(program, other) == [
        ("Before Set 1", None, [], "P5", [("Chimes", ["D5"])]),
        ("Reset after Set 1", None, [], None, []),
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
        ("Reset after Set 1", "P4", [("Chimes", ["C5"])], None, []),
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
    assert "Reset after Set 1" in body
    assert "you end Set 1 at P5 - D5/E5 on Piece 1" in body
    assert "you start Set 2 at P2 - E4/F4 on Piece 2" in body
    assert "<strong>Chimes:</strong> E4" in body
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
    assert "<h2>Reset after Set 1</h2>" in body
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
    assert [(end, start) for _, end, _, start, _ in amy_rows] == [
        (None, None),
        (None, "P2"),
    ]
    assert [(end, start) for _, end, _, start, _ in zoe_rows] == [
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
    assert "you start Set 2 at P2 - E4/F4 on Piece 2" in body


def test_everyones_resets_404_without_sets(client, db, admin_user, program, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    url = f"/programs/{program.id}/reports/everyones-resets"
    assert client.get(url).status_code == 404
