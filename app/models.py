from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import color, db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    entries = db.relationship("Entry", back_populates="user")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Concert(db.Model):
    __tablename__ = "concerts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)

    pieces = db.relationship(
        "Piece",
        back_populates="concert",
        order_by="Piece.program_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Concert {self.name}>"


piece_instrument_types = db.Table(
    "piece_instrument_types",
    db.Column("piece_id", db.Integer, db.ForeignKey("pieces.id"), primary_key=True),
    db.Column(
        "instrument_type_id",
        db.Integer,
        db.ForeignKey("instrument_types.id"),
        primary_key=True,
    ),
)


class Piece(db.Model):
    __tablename__ = "pieces"
    __table_args__ = (db.UniqueConstraint("concert_id", "program_order"),)

    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey("concerts.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    program_order = db.Column(db.Integer, nullable=False)

    concert = db.relationship("Concert", back_populates="pieces")
    instrument_types = db.relationship(
        "InstrumentType", secondary=piece_instrument_types, back_populates="pieces"
    )
    entries = db.relationship(
        "Entry", back_populates="piece", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Piece {self.title}>"


class InstrumentType(db.Model):
    __tablename__ = "instrument_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # "pitch": ringers pick chromatic pitches from note_range_low..high.
    # "color": ringers pick counts of named mallet colors (app/color.py);
    # the note range columns are unused and left null.
    selection_mode = db.Column(db.String(10), nullable=False, default="pitch")
    note_range_low = db.Column(db.String(10), nullable=True)
    note_range_high = db.Column(db.String(10), nullable=True)

    pieces = db.relationship(
        "Piece", secondary=piece_instrument_types, back_populates="instrument_types"
    )
    cases = db.relationship(
        "Case", back_populates="instrument_type", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<InstrumentType {self.name}>"


class Case(db.Model):
    __tablename__ = "cases"

    id = db.Column(db.Integer, primary_key=True)
    instrument_type_id = db.Column(
        db.Integer, db.ForeignKey("instrument_types.id"), nullable=False
    )
    case_number = db.Column(db.String(20), unique=True, nullable=False)
    note_range_low = db.Column(db.String(10), nullable=False)
    note_range_high = db.Column(db.String(10), nullable=False)

    instrument_type = db.relationship("InstrumentType", back_populates="cases")

    def __repr__(self):
        return f"<Case {self.case_number}>"


class Entry(db.Model):
    """A ringer's assignment + equipment sign-up for one piece.

    Created by an admin (user, piece, position) via Flask-Admin; the ringer
    only ever edits the equipment fields on an already-existing row.
    """

    __tablename__ = "entries"
    __table_args__ = (db.UniqueConstraint("user_id", "piece_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    piece_id = db.Column(db.Integer, db.ForeignKey("pieces.id"), nullable=False)
    position = db.Column(db.String(20), nullable=False)
    misc_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="entries")
    piece = db.relationship("Piece", back_populates="entries")
    instrument_selections = db.relationship(
        "EntryInstrument", back_populates="entry", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Entry user={self.user_id} piece={self.piece_id} position={self.position}>"


class EntryInstrument(db.Model):
    """The specific pitches a ringer plays on one instrument type for an entry."""

    __tablename__ = "entry_instruments"
    __table_args__ = (db.UniqueConstraint("entry_id", "instrument_type_id"),)

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("entries.id"), nullable=False)
    instrument_type_id = db.Column(
        db.Integer, db.ForeignKey("instrument_types.id"), nullable=False
    )
    notes = db.Column(db.Text, nullable=True)

    entry = db.relationship("Entry", back_populates="instrument_selections")
    instrument_type = db.relationship("InstrumentType")

    def note_list(self):
        """Pitch names for a pitch-mode instrument type."""
        return [n for n in (self.notes or "").split(",") if n]

    def color_counts(self):
        """`[(label, count), ...]` for a color-mode instrument type."""
        return color.parse_color_counts(self.notes)

    def __repr__(self):
        return f"<EntryInstrument entry={self.entry_id} type={self.instrument_type_id}>"
