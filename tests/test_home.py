import re

import pytest
import sqlalchemy as sa
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, add_piece, login

from app.models import Cycle, Entry, EntryInstrument, Piece, Program, ProgramPiece


def _cycle_url(program):
    return f"/cycles/{program.cycle_id}"


# --- home page -----------------------------------------------------------


def test_home_shows_active_cycle_and_its_programs(client, db, ringer, cycle, program):
    db.session.add(Cycle(name="Old Cycle"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get("/").get_data(as_text=True)

    assert cycle.name in body
    assert "Old Cycle" not in body
    assert program.name in body
    assert f'href="/cycles/{cycle.id}"' in body
    assert "Edit my equipment" in body


def test_home_lists_programs_by_date(client, db, ringer, cycle):
    from datetime import datetime

    db.session.add_all(
        [
            Program(cycle=cycle, name="Second", datetime=datetime(2026, 5, 9, 19, 30)),
            Program(cycle=cycle, name="First", datetime=datetime(2026, 5, 2, 15, 0)),
        ]
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get("/").get_data(as_text=True)

    assert body.index("First") < body.index("Second")
    assert "Sat, May 9, 2026, 7:30 PM" in body


def test_home_without_an_active_cycle(client, db, ringer):
    db.session.add(Cycle(name="Dormant", active=False))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get("/").get_data(as_text=True)

    assert "no active cycle" in body
    assert "Dormant" not in body


def test_report_buttons_are_admin_only(client, admin_user, ringer, program):
    report_url = f"/programs/{program.id}/reports/cases-list"

    login(client, ringer, RINGER_PASSWORD)
    assert report_url not in client.get("/").get_data(as_text=True)
    client.post("/logout")

    login(client, admin_user, ADMIN_PASSWORD)
    assert report_url in client.get("/").get_data(as_text=True)


# --- one active cycle ----------------------------------------------------


def test_activating_a_cycle_deactivates_the_old_one(db, cycle):
    newer = Cycle(name="Fall 2026", active=True)
    db.session.add(newer)
    db.session.commit()

    db.session.refresh(cycle)
    assert cycle.active is False
    assert Cycle.get_active() == newer


def test_reactivating_a_lower_id_cycle(db, cycle):
    newer = Cycle(name="Fall 2026", active=True)
    db.session.add(newer)
    db.session.commit()

    cycle.active = True
    db.session.commit()

    db.session.refresh(newer)
    assert newer.active is False
    assert Cycle.get_active() == cycle


def test_database_rejects_two_active_cycles(db, cycle):
    with pytest.raises(sa.exc.IntegrityError):
        db.session.execute(
            sa.text("INSERT INTO cycles (name, active) VALUES ('Rogue', true)")
        )
    db.session.rollback()


def test_admin_activating_a_cycle_moves_active(client, db, admin_user, cycle):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post("/admin/cycle/new/", data={"name": "Fall 2026", "active": "y"})

    assert Cycle.get_active().name == "Fall 2026"
    db.session.refresh(cycle)
    assert cycle.active is False


# --- program admin -------------------------------------------------------


def test_admin_rejects_a_piece_from_another_cycle(client, db, admin_user, program):
    other = Cycle(name="Fall 2026")
    stray = Piece(title="Stray")
    other.pieces.append(stray)
    db.session.add(other)
    db.session.commit()

    login(client, admin_user, ADMIN_PASSWORD)
    response = client.post(
        f"/admin/program/edit/?id={program.id}",
        data={
            "cycle": program.cycle_id,
            "name": program.name,
            "program_pieces-0-piece": stray.id,
            "program_pieces-0-position": 1,
        },
        follow_redirects=True,
    )

    assert "a program can only play its own" in response.get_data(as_text=True)
    db.session.rollback()
    assert ProgramPiece.query.count() == 0


def test_program_admin_labels_piece_order_as_order(client, admin_user, program, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/admin/program/edit/?id={program.id}").get_data(as_text=True)

    assert re.search(r'<label[^>]*for="program_pieces-0-position"[^>]*>\s*Order', body)
    assert re.search(r'for="program_pieces-0-position"[^>]*>\s*Position', body) is None


def test_admin_sets_program_pieces_and_order(client, db, admin_user, program):
    first = add_piece(db, program, "First", 1)
    second = add_piece(db, program, "Second", 2)
    db.session.commit()
    first_pp, second_pp = program.program_pieces

    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        f"/admin/program/edit/?id={program.id}",
        data={
            "cycle": program.cycle_id,
            "name": program.name,
            "program_pieces-0-id": first_pp.id,
            "program_pieces-0-piece": first.id,
            "program_pieces-0-position": 2,
            "program_pieces-1-id": second_pp.id,
            "program_pieces-1-piece": second.id,
            "program_pieces-1-position": 1,
        },
    )

    db.session.expire_all()
    assert [p.title for p in db.session.get(Program, program.id).pieces] == [
        "Second",
        "First",
    ]


# --- program equipment view ----------------------------------------------


def test_program_view_follows_each_programs_order(client, db, ringer, cycle, program):
    a = add_piece(db, program, "Alpha", 1)
    b = add_piece(db, program, "Beta", 2)
    c = add_piece(db, program, "Gamma", 3)
    later = Program(cycle=cycle, name="Later Concert")
    db.session.add_all(
        [
            later,
            ProgramPiece(program=later, piece=c, position=1),
            ProgramPiece(program=later, piece=a, position=2),
        ]
    )
    for piece in (a, b, c):
        db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    first = client.get(f"/programs/{program.id}/my-equipment").get_data(as_text=True)
    second = client.get(f"/programs/{later.id}/my-equipment").get_data(as_text=True)

    assert first.index("1. Alpha") < first.index("2. Beta") < first.index("3. Gamma")
    assert second.index("1. Gamma") < second.index("2. Alpha")
    assert "Beta" not in second


# --- program order page --------------------------------------------------


def test_home_links_each_program_to_its_order(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    body = client.get("/").get_data(as_text=True)

    assert f'href="/programs/{program.id}/order"' in body
    assert "View my equipment" in body


def test_program_order_lists_every_piece_in_order(client, db, ringer, cycle, program):
    add_piece(db, program, "Alpha", 2)
    add_piece(db, program, "Beta", 1)
    # In the cycle but not this program.
    cycle.pieces.append(Piece(title="Not Yet Placed"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/order").get_data(as_text=True)

    assert body.index("1. Beta") < body.index("2. Alpha")
    assert "Not Yet Placed" not in body


def test_program_order_shown_to_admin_with_no_pieces(client, db, admin_user, program):
    add_piece(db, program, "Alpha", 1)
    db.session.commit()

    login(client, admin_user, ADMIN_PASSWORD)
    body = client.get(f"/programs/{program.id}/order").get_data(as_text=True)

    assert "1. Alpha" in body


def test_program_order_for_an_empty_program(client, ringer, program):
    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/programs/{program.id}/order").get_data(as_text=True)

    assert "No pieces have been added" in body


def test_program_order_404s_for_unknown_program(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    assert client.get("/programs/999999/order").status_code == 404


def test_program_order_requires_login(client, program):
    response = client.get(f"/programs/{program.id}/order", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- cycle (edit equipment) page -----------------------------------------


def test_cycle_page_lists_pieces_from_every_program(client, db, ringer, cycle, program):
    in_program = add_piece(db, program, "In Program", 1)
    unplaced = Piece(title="Not Yet Placed")
    cycle.pieces.append(unplaced)
    elsewhere = Cycle(name="Other")
    other_piece = Piece(title="Other Cycle Piece")
    elsewhere.pieces.append(other_piece)
    db.session.add(elsewhere)
    db.session.commit()
    for piece in (in_program, unplaced, other_piece):
        db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    body = client.get(f"/cycles/{cycle.id}").get_data(as_text=True)

    assert "In Program" in body
    assert "Not Yet Placed" in body
    assert "Other Cycle Piece" not in body


def test_cycle_page_only_shows_pieces_ringer_is_assigned_to(
    client, db, ringer, program, instrument_type
):
    assigned = add_piece(db, program, "Assigned Piece", 1)
    add_piece(db, program, "Unassigned Piece", 2)
    db.session.commit()
    db.session.add(Entry(user_id=ringer.id, piece_id=assigned.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Assigned Piece" in response.data
    assert b"Unassigned Piece" not in response.data


def test_cycle_page_shows_position(client, db, ringer, program, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="LB2"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"LB2" in response.data


def test_float_position_has_no_entry_link(client, db, ringer, program, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="Float"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Float" in response.data
    entry_url = f"/pieces/{piece.id}/entry".encode()
    assert entry_url not in response.data


def test_no_checkmark_before_equipment_is_saved(client, db, ringer, program, piece):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Equipment saved" not in response.data


def test_checkmark_when_instruments_saved(
    client, db, ringer, program, piece, instrument_type
):
    entry = Entry(user_id=ringer.id, piece_id=piece.id, position="P1")
    db.session.add(entry)
    db.session.add(
        EntryInstrument(entry=entry, instrument_type_id=instrument_type.id, notes="C4")
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Equipment saved" in response.data


def test_checkmark_when_only_misc_notes_saved(client, db, ringer, program, piece):
    db.session.add(
        Entry(
            user_id=ringer.id, piece_id=piece.id, position="P1", misc_notes="Bell tree"
        )
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Equipment saved" in response.data


def test_checkmark_when_saved_with_nothing_selected(
    client, db, ringer, program, piece
):
    db.session.add(Entry(user_id=ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    client.post(f"/pieces/{piece.id}/entry", data={"misc_notes": ""})
    response = client.get(_cycle_url(program))

    assert b"Equipment saved" in response.data


def test_blank_misc_notes_do_not_count(client, db, ringer, program, piece):
    db.session.add(
        Entry(user_id=ringer.id, piece_id=piece.id, position="P1", misc_notes="  ")
    )
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert b"Equipment saved" not in response.data


def test_ringer_does_not_see_another_ringers_entries(
    client, db, ringer, other_ringer, program, piece
):
    db.session.add(Entry(user_id=other_ringer.id, piece_id=piece.id, position="P1"))
    db.session.commit()

    login(client, ringer, RINGER_PASSWORD)
    response = client.get(_cycle_url(program))

    assert piece.title.encode() not in response.data


def test_cycle_page_404s_for_unknown_concert(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get("/concerts/999999")
    assert response.status_code == 404
