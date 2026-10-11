import os

import pytest

from app import create_app
from app import db as _db
from app.models import Cycle, InstrumentType, Piece, Program, ProgramPiece, User

RINGER_PASSWORD = "ringerpass123"
ADMIN_PASSWORD = "adminPassword456"

# The bell_tracker_test database created by docker/initdb/01-test-db.sql.
# Start it with `docker compose up -d db`.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://bell:bell@localhost:5432/bell_tracker_test",
)


@pytest.fixture()
def test_database_url():
    return TEST_DATABASE_URL


@pytest.fixture()
def app():
    """A Flask app on the Postgres test database, schema rebuilt per test.

    Postgres rather than SQLite so the suite exercises the dialect we
    actually deploy on. Every test drops and recreates the schema, so they
    share the database but never each other's rows - which also means they
    can't run in parallel.
    """
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
        }
    )
    with application.app_context():
        _db.drop_all()
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def admin_user(db):
    user = User(email="admin@example.com", name="Admin", is_admin=True)
    user.set_password(ADMIN_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def ringer(db):
    user = User(email="ringer@example.com", name="Ringer One", is_admin=False)
    user.set_password(RINGER_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def manager(db):
    user = User(email="manager@example.com", name="Manager", is_manager=True)
    user.set_password(RINGER_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def other_ringer(db):
    user = User(email="ringer2@example.com", name="Ringer Two", is_admin=False)
    user.set_password(RINGER_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def instrument_type(db):
    it = InstrumentType(
        name="Chimes", note_range_low="C4", note_range_high="C6", display_order=20
    )
    db.session.add(it)
    db.session.commit()
    return it


@pytest.fixture()
def mallet_instrument_type(db):
    it = InstrumentType(name="Mallets", selection_mode="color", enabled_by_default=True)
    db.session.add(it)
    db.session.commit()
    return it


@pytest.fixture()
def bass_instrument_type(db):
    it = InstrumentType(
        name="Bass Bells",
        note_range_low="C2",
        note_range_high="C4",
        position_prefix="LB",
        enabled_by_default=True,
        display_order=10,
    )
    db.session.add(it)
    db.session.commit()
    return it


@pytest.fixture()
def cycle(db):
    c = Cycle(name="Spring 2026", active=True)
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture()
def program(db, cycle):
    p = Program(cycle=cycle, name="Spring Concert")
    db.session.add(p)
    db.session.commit()
    return p


def add_piece(db, program, title, position, **kwargs):
    """A new piece in `program`'s cycle, placed in `program` at `position`.

    Added to the session but not committed.
    """
    piece = Piece(cycle_id=program.cycle_id, title=title, **kwargs)
    db.session.add(piece)
    db.session.add(ProgramPiece(program=program, piece=piece, position=position))
    return piece


@pytest.fixture()
def piece(db, program, instrument_type):
    p = add_piece(db, program, "Ode to Joy", 1)
    p.instrument_types.append(instrument_type)
    db.session.commit()
    return p


@pytest.fixture()
def mallet_piece(db, program, mallet_instrument_type):
    p = add_piece(db, program, "Toccata", 2)
    p.instrument_types.append(mallet_instrument_type)
    db.session.commit()
    return p


def login(client, user, password):
    return client.post(
        "/login",
        data={"email": user.email, "password": password},
        follow_redirects=True,
    )
