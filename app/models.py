from datetime import datetime, timezone
import re

from flask_login import UserMixin
import sqlalchemy as sa
from sqlalchemy import event
from werkzeug.security import check_password_hash, generate_password_hash

from app import color, db, pitch


def utcnow():
    return datetime.now(timezone.utc)


# Instrument types sort by display_order; this default parks anything
# unranked at the end, behind the bells.
DEFAULT_DISPLAY_ORDER = 100
# What a ticked checkbox-mode selection stores in EntryInstrument.notes. An
# unticked box stores no row at all.
CHECKED_NOTES = "yes"
# Ringers never sign up for the main bells: they're always on the tables,
# so the type is kept off the equipment form.
MAIN_BELLS = "Main Bells"
BASS_BELLS = "Bass Bells"
# Every case of these types goes on the cases used list, whatever was
# signed up for.
ALWAYS_LISTED_CASE_TYPES = {MAIN_BELLS, BASS_BELLS}


def _first_word_of_name(context):
    """Default first_name for users created without one (the CLI, tests).

    Flask-Admin also calls column defaults with no context to prefill its
    create form; there's no name yet then, so the field starts empty.
    """
    if context is None:
        return ""
    parts = (context.get_current_parameters().get("name") or "").split()
    return parts[0] if parts else ""


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    # What the roster spreadsheets call this ringer; the position importer
    # matches on it, so it should be unique among ringers.
    first_name = db.Column(db.String(80), nullable=False, default=_first_word_of_name)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    # Managers see every program's reports but not the admin panel.
    is_manager = db.Column(
        db.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    # Set when an admin hands out a password; the user is held on the
    # change-password page until they pick their own.
    must_change_password = db.Column(
        db.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    created_at = db.Column(db.DateTime, default=utcnow)

    entries = db.relationship("Entry", back_populates="user")

    @property
    def can_view_reports(self):
        return self.is_admin or self.is_manager

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Cycle(db.Model):
    """A season's worth of rehearsal: a repertoire of pieces, played across
    several programs. At most one cycle is active, and that's the one
    ringers see when they log in."""

    __tablename__ = "cycles"
    __table_args__ = (
        # Only one row may have active = true.
        db.Index(
            "uq_cycles_one_active",
            "active",
            unique=True,
            postgresql_where=sa.text("active"),
            sqlite_where=sa.text("active"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    active = db.Column(
        db.Boolean, nullable=False, default=False, server_default=sa.false()
    )

    programs = db.relationship(
        "Program",
        back_populates="cycle",
        order_by="(Program.datetime, Program.id)",
        cascade="all, delete-orphan",
    )
    pieces = db.relationship(
        "Piece",
        back_populates="cycle",
        order_by="Piece.title",
        cascade="all, delete-orphan",
    )

    @classmethod
    def get_active(cls):
        return cls.query.filter_by(active=True).first()

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<Cycle {self.name}>"


class Program(db.Model):
    """One performance in a cycle, playing some of the cycle's pieces in
    its own order."""

    __tablename__ = "programs"

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    # Nullable because programs carried over from the old concerts table
    # had no date.
    datetime = db.Column(db.DateTime, nullable=True)

    cycle = db.relationship("Cycle", back_populates="programs")
    program_pieces = db.relationship(
        "ProgramPiece",
        back_populates="program",
        order_by="ProgramPiece.position",
        cascade="all, delete-orphan",
    )

    @property
    def pieces(self):
        """The program's pieces in program order."""
        return [pp.piece for pp in self.program_pieces]

    def when_label(self):
        """e.g. "Sat, May 9, 2026, 7:30 PM", or "" with no date set."""
        dt = self.datetime
        if dt is None:
            return ""
        hour = dt.hour % 12 or 12
        return f"{dt:%a, %b} {dt.day}, {dt.year}, {hour}:{dt:%M %p}"

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<Program {self.name}>"


class ProgramPiece(db.Model):
    """A piece's place in a program."""

    __tablename__ = "program_pieces"
    # No unique constraint on position, so an admin can swap two pieces'
    # numbers in one save.
    __table_args__ = (db.UniqueConstraint("program_id", "piece_id"),)

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=False)
    piece_id = db.Column(db.Integer, db.ForeignKey("pieces.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)

    program = db.relationship("Program", back_populates="program_pieces")
    piece = db.relationship("Piece", back_populates="program_pieces")

    def __repr__(self):
        return f"<ProgramPiece program={self.program_id} piece={self.piece_id} #{self.position}>"


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

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)

    cycle = db.relationship("Cycle", back_populates="pieces")
    program_pieces = db.relationship(
        "ProgramPiece", back_populates="piece", cascade="all, delete-orphan"
    )
    instrument_types = db.relationship(
        "InstrumentType",
        secondary=piece_instrument_types,
        back_populates="pieces",
        order_by="(InstrumentType.display_order, InstrumentType.name)",
    )
    entries = db.relationship(
        "Entry", back_populates="piece", cascade="all, delete-orphan"
    )

    def __str__(self):
        # Admin select boxes list pieces from every cycle, so say which.
        return f"{self.title} ({self.cycle.name})" if self.cycle else self.title

    def __repr__(self):
        return f"<Piece {self.title}>"


class InstrumentType(db.Model):
    __tablename__ = "instrument_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # "pitch": ringers pick chromatic pitches from note_range_low..high.
    # "color": ringers pick counts of named mallet colors (app/color.py);
    # the note range columns are unused and left null.
    # "checkbox": ringers tick whether they need one (singing bell sticks);
    # no note range either.
    # "options": ringers tick any of the type's InstrumentOptions, which
    # the admin manages (percussion: triangle, slap stick, ...). No note
    # range either.
    selection_mode = db.Column(db.String(10), nullable=False, default="pitch")
    note_range_low = db.Column(db.String(10), nullable=True)
    note_range_high = db.Column(db.String(10), nullable=True)
    # What the ringer's equipment form calls the type, when that should
    # differ from its name ("Singing Bell Stick" for a single tick). Null
    # means use the name.
    form_label = db.Column(db.String(100), nullable=True)
    # When set, only ringers whose position starts with this string see the
    # type - "LB" for bass bells. Null means everyone on the piece sees it.
    position_prefix = db.Column(db.String(10), nullable=True)
    # Attach this type to every newly created piece.
    enabled_by_default = db.Column(db.Boolean, nullable=False, default=False)
    # Where this type sits on a ringer's equipment form, low to high. The
    # bells are numbered in tens so an admin can slot something between two
    # of them; anything left at the default sorts to the end, which is
    # where mallets and any newly added type belong.
    display_order = db.Column(db.Integer, nullable=False, default=DEFAULT_DISPLAY_ORDER)

    pieces = db.relationship(
        "Piece", secondary=piece_instrument_types, back_populates="instrument_types"
    )
    cases = db.relationship(
        "Case", back_populates="instrument_type", cascade="all, delete-orphan"
    )
    options = db.relationship(
        "InstrumentOption",
        back_populates="instrument_type",
        cascade="all, delete-orphan",
        order_by="InstrumentOption.name",
    )

    def label_on_form(self):
        return self.form_label or self.name

    def __repr__(self):
        return f"<InstrumentType {self.name}>"


class InstrumentOption(db.Model):
    """One thing a ringer can pick on an options-mode instrument type, such
    as Triangle under Percussion."""

    __tablename__ = "instrument_options"
    __table_args__ = (db.UniqueConstraint("instrument_type_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    instrument_type_id = db.Column(
        db.Integer, db.ForeignKey("instrument_types.id"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)

    instrument_type = db.relationship("InstrumentType", back_populates="options")

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<InstrumentOption {self.name}>"


@event.listens_for(db.session, "before_flush")
def _enable_default_instrument_types_on_new_pieces(session, flush_context, instances):
    """Enable every `enabled_by_default` instrument type on new pieces.

    Pieces get created from two different admin paths - the Piece view and
    the roster import - so the default lives here rather than in either
    one. It only fires for pieces being inserted, so an
    admin can still remove a type from a piece that doesn't use it.
    """
    new_pieces = [obj for obj in session.new if isinstance(obj, Piece)]
    if not new_pieces:
        return
    with session.no_autoflush:
        default_types = (
            session.query(InstrumentType).filter_by(enabled_by_default=True).all()
        )
        for piece in new_pieces:
            for instrument_type in default_types:
                if instrument_type not in piece.instrument_types:
                    piece.instrument_types.append(instrument_type)


@event.listens_for(db.session, "before_flush")
def _deactivate_other_cycles(session, flush_context, instances):
    """Activating a cycle deactivates whichever one was active.

    The old row is cleared with a direct UPDATE ahead of the flush: left to
    the unit of work, the two rows' UPDATEs go in primary-key order, and if
    the new one ran first the one-active index would reject it.
    """
    activated = [
        obj
        for obj in (*session.new, *session.dirty)
        if isinstance(obj, Cycle) and obj.active
    ]
    if not activated:
        return
    keep_ids = [c.id for c in activated if c.id is not None]
    table = Cycle.__table__
    session.connection().execute(
        sa.update(table)
        .where(table.c.active.is_(True), table.c.id.notin_(keep_ids))
        .values(active=False)
    )
    for obj in list(session.identity_map.values()):
        if isinstance(obj, Cycle) and obj not in activated:
            session.expire(obj, ["active"])


class Case(db.Model):
    __tablename__ = "cases"

    id = db.Column(db.Integer, primary_key=True)
    instrument_type_id = db.Column(
        db.Integer, db.ForeignKey("instrument_types.id"), nullable=False
    )
    case_number = db.Column(db.String(20), unique=True, nullable=False)
    note_range_low = db.Column(db.String(10), nullable=False)
    note_range_high = db.Column(db.String(10), nullable=False)
    # Some cases hold a second, separate run of bells. Both are null for a
    # single-range case and both are set when there's a second run.
    second_range_low = db.Column(db.String(10), nullable=True)
    second_range_high = db.Column(db.String(10), nullable=True)

    instrument_type = db.relationship("InstrumentType", back_populates="cases")

    def ranges(self):
        """`[(low, high), ...]` for each run of bells in the case."""
        result = [(self.note_range_low, self.note_range_high)]
        if self.second_range_low and self.second_range_high:
            result.append((self.second_range_low, self.second_range_high))
        return result

    def covers(self, name):
        """Whether pitch `name` falls in any of the case's ranges."""
        return any(pitch.in_range(name, low, high) for low, high in self.ranges())

    def sort_key(self):
        """Orders case numbers by their numeric parts, so B2 comes before
        B10 rather than after it as plain text would put it."""
        # Splitting on a captured group alternates text and digits, so the
        # digit runs always sit at odd indexes and compare as ints.
        return [
            int(part) if i % 2 else part
            for i, part in enumerate(re.split(r"(\d+)", self.case_number))
        ]

    def range_label(self):
        """Display form, e.g. "C4-D4" or "C4-D4, A5-C6"."""
        return ", ".join(f"{low}-{high}" for low, high in self.ranges())

    def validation_error(self):
        """Why this case can't be saved as-is, or None if it can.

        Shared by the admin form and the seed loader (app/case_seed.py).
        """
        instrument_type = self.instrument_type
        if instrument_type.selection_mode != "pitch":
            return "Cases only apply to pitch-based instrument types."
        if bool(self.second_range_low) != bool(self.second_range_high):
            return "A second range needs both a low and a high note."
        type_low = instrument_type.note_range_low
        type_high = instrument_type.note_range_high
        for low, high in self.ranges():
            if pitch.pitch_index(low) > pitch.pitch_index(high):
                return "Low note must not be above the high note."
            if not pitch.in_range(low, type_low, type_high) or not pitch.in_range(
                high, type_low, type_high
            ):
                return (
                    f"Case range must fall within {instrument_type.name}'s "
                    f"range ({type_low}-{type_high})."
                )
        return None

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

    def has_equipment(self):
        """Whether the ringer has saved any equipment on this piece."""
        return bool(self.instrument_selections) or bool(
            self.misc_notes and self.misc_notes.strip()
        )

    def sorted_instrument_selections(self):
        """Selections in the same order as the equipment form."""
        return sorted(
            self.instrument_selections,
            key=lambda s: (s.instrument_type.display_order, s.instrument_type.name),
        )

    def visible_instrument_types(self):
        """Instrument types this ringer sees on their equipment form.

        A type carrying a position_prefix (bass bells with "LB") is limited
        to positions starting with it; Main Bells is never shown; everything
        else is shown to everyone on the piece. Presentation only - reports
        still count a hidden type's selections.

        Order comes from InstrumentType.display_order via the piece's
        relationship, so filtering here preserves it.
        """
        return [
            t
            for t in self.piece.instrument_types
            if t.name != MAIN_BELLS
            and (not t.position_prefix or self.position.startswith(t.position_prefix))
        ]

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

    def selected_options(self):
        """The InstrumentOptions ticked on an options-mode instrument type,
        in the type's order. Notes hold option ids, so renaming an option
        carries over; one the admin has since deleted drops out.
        """
        ids = set(self.note_list())
        return [o for o in self.instrument_type.options if str(o.id) in ids]

    def __repr__(self):
        return f"<EntryInstrument entry={self.entry_id} type={self.instrument_type_id}>"
