import io
import pathlib

import pytest
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

from app import roster_import
from app.models import Entry, Piece, User
from werkzeug.security import generate_password_hash

SAMPLE_CSV = (pathlib.Path(__file__).parent / "fixtures" / "roster_sample.csv").read_text()
# Hashed once: real hashing per user would make each test create 15 users
# slowly, and these tests never log in as them.
PASSWORD_HASH = generate_password_hash("unused-password")
SAMPLE_FIRST_NAMES = [
    "Alice", "Ben", "Clara", "Dmitri", "Esme", "Felix", "Greta", "Hugo",
    "Iris", "Jonah", "Kofi", "Lena", "Milo", "Nora", "Oscar",
]


def _user(db, name):
    user = User(
        email=f"{name.lower().replace(' ', '.')}@example.com",
        name=name,
        password_hash=PASSWORD_HASH,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def sample_ringers(db):
    return {name: _user(db, f"{name} Ringer") for name in SAMPLE_FIRST_NAMES}


def _plan(concert, text):
    return roster_import.plan_import(concert, text)


# --- planning ---


def test_sample_sheet_plans_cleanly(db, concert, sample_ringers):
    plan = _plan(concert, SAMPLE_CSV)

    assert plan.errors == []
    assert len(plan.new_piece_titles) == 13
    assert plan.new_piece_titles[0] == "Aurora Fanfare"
    assert "Stars, Stones and Rivers" in plan.new_piece_titles
    assert plan.count(roster_import.ADD) == len(plan.assignments)
    assert plan.can_apply


def test_sample_sheet_applies(db, concert, sample_ringers):
    plan = _plan(concert, SAMPLE_CSV)
    roster_import.apply_import(concert, plan)

    gaudete = Piece.query.filter_by(concert_id=concert.id, title="Aurora Fanfare").one()
    positions = {e.user.name.split()[0]: e.position for e in gaudete.entries}
    assert positions["Ben"] == "LB2"
    assert positions["Nora"] == "P1"
    assert positions["Lena"] == "Other"
    assert positions["Clara"] == "Float"
    assert positions["Dmitri"] == "P3"

    driftwood = Piece.query.filter_by(title="Driftwood Waltz").one()
    floats = sorted(
        e.user.name.split()[0] for e in driftwood.entries if e.position == "Float"
    )
    assert floats == ["Ben", "Kofi"]


def test_new_pieces_follow_existing_program_order(db, concert, piece, sample_ringers):
    csv_text = "Position,Ode to Joy,Brand New Piece\nP1,Nora,Clara\n"
    roster_import.apply_import(concert, _plan(concert, csv_text))

    new_piece = Piece.query.filter_by(title="Brand New Piece").one()
    assert new_piece.program_order == piece.program_order + 1
    assert Piece.query.filter_by(concert_id=concert.id).count() == 2


def test_existing_piece_matched_ignoring_case_and_spaces(db, concert, piece, sample_ringers):
    plan = _plan(concert, "Position,  ode to   JOY \nP1,Nora\n")
    assert plan.new_piece_titles == []
    assert plan.errors == []


def test_updates_changed_positions_and_keeps_equipment(
    db, concert, piece, sample_ringers
):
    sam = sample_ringers["Nora"]
    entry = Entry(user_id=sam.id, piece_id=piece.id, position="P1", misc_notes="Tree")
    drew_entry = Entry(user_id=sample_ringers["Clara"].id, piece_id=piece.id, position="P2")
    db.session.add_all([entry, drew_entry])
    db.session.commit()

    plan = _plan(concert, "Position,Ode to Joy\nP4,Nora\nP2,Clara\n")
    assert plan.count(roster_import.UPDATE) == 1
    assert plan.count(roster_import.UNCHANGED) == 1
    roster_import.apply_import(concert, plan)

    db.session.refresh(entry)
    assert entry.position == "P4"
    assert entry.misc_notes == "Tree"


def test_never_removes_assignments_missing_from_sheet(
    db, concert, piece, sample_ringers
):
    db.session.add(
        Entry(user_id=sample_ringers["Greta"].id, piece_id=piece.id, position="P5")
    )
    db.session.commit()

    roster_import.apply_import(concert, _plan(concert, "Position,Ode to Joy\nP1,Nora\n"))

    assert Entry.query.filter_by(piece_id=piece.id).count() == 2


def test_nothing_to_change_cannot_apply(db, concert, piece, sample_ringers):
    db.session.add(
        Entry(user_id=sample_ringers["Nora"].id, piece_id=piece.id, position="P1")
    )
    db.session.commit()
    plan = _plan(concert, "Position,Ode to Joy\nP1,Nora\n")
    assert plan.errors == []
    assert not plan.can_apply


@pytest.mark.parametrize(
    "csv_text, message",
    [
        ("Position,Ode to Joy\nP99,Nora\n", 'Unknown position "P99"'),
        ("Position,Ode to Joy\nAux,Nora\n", 'Unknown position "Aux"'),
        ("Position,Ode to Joy\nP1,Zelda\n", 'no ringer named "Zelda"'),
        ("Position,Ode to Joy\nP1,Nora\nP2,Nora\n", "listed at both P1 and P2"),
        ("Position,Ode to Joy,ode to joy\nP1,Nora,Clara\n", "more than one column"),
        ("", "The file is empty."),
        ("Position\nP1\n", "should list the piece titles"),
    ],
)
def test_problems_are_reported_and_block_import(
    db, concert, piece, sample_ringers, csv_text, message
):
    plan = _plan(concert, csv_text)
    assert any(message in e for e in plan.errors), plan.errors
    assert not plan.can_apply


def test_ambiguous_first_name_is_an_error(db, concert, piece, sample_ringers):
    _user(db, "Nora Other")
    plan = _plan(concert, "Position,Ode to Joy\nP1,Nora\n")
    assert any("matches more than one ringer" in e for e in plan.errors)


def test_stray_spaces_around_positions_and_names_are_ignored(
    db, concert, piece, sample_ringers
):
    plan = _plan(concert, "Position,Ode to Joy\nP3 ,  Nora \n")
    assert plan.errors == []
    assert plan.assignments[0].position == "P3"


def test_first_name_match_ignores_case(db, concert, piece, sample_ringers):
    plan = _plan(concert, "Position,Ode to Joy\nlb1,nORA\n")
    assert plan.errors == []
    assert plan.assignments[0].position == "LB1"


# --- admin page ---

URL = "/admin/roster_import/"


def _upload(client, concert, text, filename="roster.csv"):
    return client.post(
        URL,
        data={
            "concert_id": concert.id,
            "file": (io.BytesIO(text.encode("utf-8-sig")), filename),
        },
        content_type="multipart/form-data",
    )


def test_import_page_is_admin_only(client, ringer):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(URL)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_upload_shows_preview_without_saving(
    client, db, admin_user, concert, piece, sample_ringers
):
    login(client, admin_user, ADMIN_PASSWORD)
    body = _upload(client, concert, SAMPLE_CSV).get_data(as_text=True)

    assert "Nothing has been saved yet" in body
    assert "Confirm import" in body
    assert "Kestrel Carol" in body
    assert Entry.query.count() == 0
    assert Piece.query.count() == 1


def test_confirm_applies_import(client, db, admin_user, concert, piece, sample_ringers):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.post(
        URL,
        data={"concert_id": concert.id, "csv_text": SAMPLE_CSV, "confirm": "1"},
        follow_redirects=True,
    )
    assert "13 pieces created" in response.get_data(as_text=True)
    assert Piece.query.filter_by(concert_id=concert.id).count() == 14
    assert Entry.query.count() > 0


def test_preview_with_errors_has_no_confirm(client, db, admin_user, concert, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    body = _upload(client, concert, "Position,Ode to Joy\nP1,Nobody\n").get_data(
        as_text=True
    )
    assert "no ringer named &#34;Nobody&#34;" in body
    assert "Confirm import" not in body


def test_confirm_with_errors_saves_nothing(client, db, admin_user, concert, piece):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        URL,
        data={
            "concert_id": concert.id,
            "csv_text": "Position,Ode to Joy,New One\nP1,Nobody,Nobody\n",
            "confirm": "1",
        },
    )
    assert Piece.query.count() == 1
    assert Entry.query.count() == 0


def test_non_utf8_upload_is_rejected(client, admin_user, concert):
    login(client, admin_user, ADMIN_PASSWORD)
    response = client.post(
        URL,
        data={"concert_id": concert.id, "file": (io.BytesIO(b"\xff\xfe\x00bad"), "x.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Save it as CSV (UTF-8)" in response.get_data(as_text=True)


def test_preview_round_trips_csv_through_confirm_form(
    client, db, admin_user, concert, piece, sample_ringers
):
    """Confirm with exactly what the preview page's hidden field carries,
    as a browser would - quotes and commas in titles must survive."""
    from html.parser import HTMLParser

    class HiddenFields(HTMLParser):
        fields = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "input" and attrs.get("type") == "hidden":
                self.fields[attrs["name"]] = attrs.get("value", "")

    login(client, admin_user, ADMIN_PASSWORD)
    parser = HiddenFields()
    parser.feed(_upload(client, concert, SAMPLE_CSV).get_data(as_text=True))
    assert parser.fields["csv_text"] == SAMPLE_CSV

    client.post(URL, data={**parser.fields, "confirm": "1"})
    assert Piece.query.filter_by(title="Stars, Stones and Rivers").count() == 1


# --- first_name ---


def test_first_name_defaults_to_first_word_of_name(db):
    assert _user(db, "Beatrix Kiddo").first_name == "Beatrix"


def test_import_matches_first_name_not_name(db, concert, piece):
    user = _user(db, "Robert Smith")
    user.first_name = "Bob"
    db.session.commit()

    assert _plan(concert, "Position,Ode to Joy\nP1,Bob\n").assignments[0].user == user
    plan = _plan(concert, "Position,Ode to Joy\nP1,Robert\n")
    assert any('no ringer named "Robert"' in e for e in plan.errors)


def test_distinct_first_names_resolve_shared_given_names(db, concert, piece):
    """Two Sams can both be imported once their first_names differ."""
    sam_a = _user(db, "Sam Adams")
    sam_b = _user(db, "Sam Brown")
    sam_b.first_name = "Sam B"
    db.session.commit()

    plan = _plan(concert, "Position,Ode to Joy\nP1,Sam\nP2,sam  b\n")
    assert plan.errors == []
    assert [a.user for a in plan.assignments] == [sam_a, sam_b]


def test_admin_sets_first_name(client, db, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        "/admin/user/new/",
        data={
            "email": "t@example.com",
            "name": "Theodora Quill",
            "first_name": "  Teddy ",
            "password": "temp12345",
        },
    )
    assert User.query.filter_by(email="t@example.com").one().first_name == "Teddy"


def test_admin_blank_first_name_uses_first_word_of_name(client, db, admin_user):
    login(client, admin_user, ADMIN_PASSWORD)
    client.post(
        "/admin/user/new/",
        data={
            "email": "t@example.com",
            "name": "Theodora Quill",
            "first_name": "",
            "password": "temp12345",
        },
    )
    assert User.query.filter_by(email="t@example.com").one().first_name == "Theodora"
