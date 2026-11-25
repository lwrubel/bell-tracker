"""Import ringer position assignments from a roster spreadsheet (CSV).

The sheet's header row names the pieces (its first cell is a label and is
ignored); each following row starts with a position code and has, under
each piece, the first name(s) of whoever rings that position, matched
against each user's first_name. "-" or a
blank cell means nobody, and several ringers can share a cell separated by
commas (typically Float).

Importing is two-step: ``plan_import`` reads the sheet and works out what
would change without touching the database, so an admin can preview it;
``apply_import`` then saves that plan. Any problem in the sheet - an
unknown position, a name that matches no ringer or several - is reported
and makes the plan unappliable, so a bad sheet never half-applies.

A ringer can be listed under more than one position for a piece, and gets
an entry for each. When a ringer's positions on a piece change, their
existing entries are moved to the new positions (keeping their equipment)
before any new ones are added.

Importing only adds and updates. Assignments not in the sheet are left
alone, as is any equipment a ringer has already saved.
"""

import csv
import io
from dataclasses import dataclass, field

from app import db
from app.models import Entry, Piece, User
from app.positions import POSITION_CODES, position_sort_key

EMPTY_CELL_VALUES = {"", "-"}

ADD = "add"
UPDATE = "update"
UNCHANGED = "unchanged"


@dataclass
class Assignment:
    piece_title: str
    user: User
    position: str
    action: str
    old_position: str | None = None


@dataclass
class ImportPlan:
    cycle_id: int
    new_piece_titles: list[str] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def can_apply(self):
        has_changes = bool(self.new_piece_titles) or any(
            a.action != UNCHANGED for a in self.assignments
        )
        return has_changes and not self.errors

    def count(self, action):
        return sum(1 for a in self.assignments if a.action == action)


def _normalize(text):
    return " ".join((text or "").split()).casefold()


def _read_rows(csv_text):
    return [
        row
        for row in csv.reader(io.StringIO(csv_text))
        if any(cell.strip() for cell in row)
    ]


def plan_import(cycle, csv_text):
    """Work out what importing ``csv_text`` into ``cycle`` would change."""
    plan = ImportPlan(cycle_id=cycle.id)
    rows = _read_rows(csv_text)
    if not rows:
        plan.errors.append("The file is empty.")
        return plan

    header, body = rows[0], rows[1:]
    titles = [cell.strip() for cell in header[1:]]
    if not any(titles):
        plan.errors.append(
            "The first row should list the piece titles, after one label cell."
        )
        return plan

    existing_pieces = {_normalize(p.title): p for p in cycle.pieces}
    seen_titles = {}
    for title in titles:
        if not title:
            continue
        key = _normalize(title)
        if key in seen_titles:
            plan.errors.append(f'Piece "{title}" appears in more than one column.')
            continue
        seen_titles[key] = title
        if key not in existing_pieces:
            plan.new_piece_titles.append(title)

    users_by_first_name = {}
    for user in User.query.order_by(User.name).all():
        users_by_first_name.setdefault(_normalize(user.first_name), []).append(user)

    positions_by_key = {code.casefold(): code for code in POSITION_CODES}

    # (piece key, user id) -> [position, ...] in sheet order.
    placed = {}
    # (piece key, title, user, position) in sheet order.
    placements = []
    for row in body:
        raw_position = row[0].strip() if row else ""
        position = positions_by_key.get(raw_position.casefold())
        if position is None:
            plan.errors.append(
                f'Unknown position "{raw_position}". Expected one of: '
                + ", ".join(POSITION_CODES)
                + "."
            )
            continue

        for title, cell in zip(titles, row[1:]):
            if not title or cell.strip() in EMPTY_CELL_VALUES:
                continue
            piece_key = _normalize(title)
            if seen_titles.get(piece_key) != title:
                continue  # a duplicate column, already reported
            for name in (n.strip() for n in cell.split(",")):
                if not name or name in EMPTY_CELL_VALUES:
                    continue
                matches = users_by_first_name.get(_normalize(name), [])
                if not matches:
                    plan.errors.append(
                        f'{title}, {position}: no ringer named "{name}".'
                    )
                    continue
                if len(matches) > 1:
                    plan.errors.append(
                        f'{title}, {position}: "{name}" matches more than one '
                        "ringer (" + ", ".join(u.name for u in matches) + ")."
                    )
                    continue
                user = matches[0]
                positions = placed.setdefault((piece_key, user.id), [])
                if position in positions:
                    plan.errors.append(
                        f"{title}: {user.name} is listed at {position} twice."
                    )
                    continue
                positions.append(position)
                placements.append((piece_key, title, user, position))

    planned = {}
    for (piece_key, user_id), positions in placed.items():
        planned.update(
            _assignments_for(
                existing_pieces.get(piece_key), piece_key, user_id, positions
            )
        )
    for piece_key, title, user, position in placements:
        action, old_position = planned[(piece_key, user.id, position)]
        plan.assignments.append(
            Assignment(title, user, position, action, old_position=old_position)
        )

    return plan


def _assignments_for(piece, piece_key, user_id, positions):
    """{(piece key, user id, position): (action, old position)} for one
    ringer's positions on one piece, given in sheet order.

    Positions they already have are unchanged. Each new position takes
    over one of their existing entries the sheet no longer lists, in
    position order, so its equipment is kept; any left over are added.
    """
    existing = []
    if piece is not None:
        existing = [
            entry.position
            for entry in Entry.query.filter_by(piece_id=piece.id, user_id=user_id)
        ]
    freed = sorted(
        (p for p in existing if p not in positions), key=position_sort_key
    )
    result = {}
    for position in positions:
        if position in existing:
            result[(piece_key, user_id, position)] = (UNCHANGED, None)
        elif freed:
            result[(piece_key, user_id, position)] = (UPDATE, freed.pop(0))
        else:
            result[(piece_key, user_id, position)] = (ADD, None)
    return result


def apply_import(cycle, plan):
    """Save a plan from ``plan_import``. The caller checks ``plan.can_apply``.

    New pieces join the cycle's repertoire only; an admin places them into
    programs afterwards.
    """
    pieces = {_normalize(p.title): p for p in cycle.pieces}
    for title in plan.new_piece_titles:
        piece = Piece(cycle=cycle, title=title)
        db.session.add(piece)
        pieces[_normalize(title)] = piece
    db.session.flush()

    for assignment in plan.assignments:
        if assignment.action == UNCHANGED:
            continue
        piece = pieces[_normalize(assignment.piece_title)]
        if assignment.action == UPDATE:
            entry = Entry.query.filter_by(
                piece_id=piece.id,
                user_id=assignment.user.id,
                position=assignment.old_position,
            ).one()
            entry.position = assignment.position
        else:
            db.session.add(
                Entry(
                    piece_id=piece.id,
                    user_id=assignment.user.id,
                    position=assignment.position,
                )
            )
    db.session.commit()
