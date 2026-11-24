from bisect import bisect_right
from collections import defaultdict

from sqlalchemy import and_
from sqlalchemy.orm import joinedload, selectinload

from app import color, pitch
from app.models import (
    ALWAYS_LISTED_CASE_TYPES,
    BASS_BELLS,
    BASS_CHIMES,
    MAIN_BELLS,
    Case,
    Entry,
    EntryInstrument,
    InstrumentType,
    Piece,
    ProgramPiece,
    piece_instrument_types,
)
from app.positions import (
    FLOAT_POSITION,
    POSITION_BASE_NOTES,
    ROSTER_POSITION_ORDER,
    position_label,
)


def _program_piece_filter(query, program):
    return query.join(ProgramPiece, ProgramPiece.piece_id == Piece.id).filter(
        ProgramPiece.program_id == program.id
    )


def _entry_instruments_for_program(program):
    """Selections on this program's pieces, leaving out any instrument type
    since removed from its piece (see Entry.current_instrument_selections)."""
    query = (
        EntryInstrument.query.join(Entry)
        .join(Piece)
        .join(
            piece_instrument_types,
            and_(
                piece_instrument_types.c.piece_id == Piece.id,
                piece_instrument_types.c.instrument_type_id
                == EntryInstrument.instrument_type_id,
            ),
        )
    )
    return _program_piece_filter(query, program).all()


def _used_pitches_by_type(program):
    """{instrument_type: {pitch, ...}} for pitch-mode types signed up in
    this program."""
    used_pitches_by_type = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program):
        if entry_instrument.instrument_type.selection_mode != "pitch":
            continue  # only pitch-mode types have cases
        used_pitches_by_type[entry_instrument.instrument_type].update(
            entry_instrument.note_list()
        )
    return used_pitches_by_type


def cases_list(program):
    """Return {instrument_type: [case, ...]} for cases whose note range
    overlaps a pitch actually used somewhere in this program, plus every
    Main Bells and Bass Bells case, which are always brought. Types in display order, cases
    by number (B2 before B10)."""
    needed = {}
    for instrument_type, used_pitches in _used_pitches_by_type(program).items():
        if instrument_type.name in ALWAYS_LISTED_CASE_TYPES:
            continue
        needed[instrument_type] = [
            case
            for case in instrument_type.cases
            if any(case.covers(p) for p in used_pitches)
        ]
    for instrument_type in InstrumentType.query.filter(
        InstrumentType.name.in_(ALWAYS_LISTED_CASE_TYPES)
    ):
        needed[instrument_type] = list(instrument_type.cases)
    return {
        instrument_type: sorted(cases, key=Case.sort_key)
        for instrument_type, cases in sorted(
            needed.items(), key=lambda item: (item[0].display_order, item[0].name)
        )
        if cases
    }


# Instrument types left out of the equipment pull list and equipment table,
# by name: Main Bells are always on the tables and Bass Bells always on the
# bass tables.
EQUIPMENT_LIST_EXCLUDED_TYPES = {MAIN_BELLS, BASS_BELLS}


def equipment_pull_list(program):
    """Return {instrument_type: ([(case, [pitch, ...]), ...], [pitch, ...])}:
    for each type, the bells to take out of each case, then any used pitches
    no case covers. Types are in display order, cases by number, pitches low
    to high. Main Bells and Bass Bells are left out.

    A pitch covered by two cases is listed under both, matching the cases
    used list, which brings both.
    """
    result = {}
    used_pitches_by_type = _used_pitches_by_type(program)
    for instrument_type in sorted(
        used_pitches_by_type, key=lambda t: (t.display_order, t.name)
    ):
        if instrument_type.name in EQUIPMENT_LIST_EXCLUDED_TYPES:
            continue
        used_pitches = sorted(
            used_pitches_by_type[instrument_type], key=pitch.pitch_index
        )
        if not used_pitches:
            continue
        cases = []
        for case in sorted(instrument_type.cases, key=Case.sort_key):
            bells = [p for p in used_pitches if case.covers(p)]
            if bells:
                cases.append((case, bells))
        uncovered = [
            p
            for p in used_pitches
            if not any(case.covers(p) for case in instrument_type.cases)
        ]
        result[instrument_type] = (cases, uncovered)
    return result


# Positions starting with this ring the bass bells.
BASS_POSITION_PREFIX = "LB"


def bass_bells(program):
    """Return [(program_piece, [(entry, bells), ...]), ...]: every piece in
    program order, each LB entry on it by position, and the bells that
    position signed up for as [(instrument_type, [pitch, ...]), ...], types
    in display order and pitches low to high. A piece with no LB positions
    has an empty list.
    """
    result = []
    for program_piece in program.program_pieces:
        piece = program_piece.piece
        entries = sorted(
            (e for e in piece.entries if e.position.startswith(BASS_POSITION_PREFIX)),
            key=lambda e: e.position,
        )
        positions = []
        for entry in entries:
            bells = [
                (
                    selection.instrument_type,
                    sorted(selection.note_list(), key=pitch.pitch_index),
                )
                for selection in entry.sorted_instrument_selections()
                if selection.instrument_type.selection_mode == "pitch"
                and selection.note_list()
            ]
            positions.append((entry, bells))
        result.append((program_piece, positions))
    return result


def _program_entries_by_piece(program):
    """{piece_id: [entry, ...]} for every entry on this program's pieces,
    with each entry's user and selections loaded."""
    entries = (
        Entry.query.join(Piece)
        .options(
            joinedload(Entry.user),
            selectinload(Entry.instrument_selections).joinedload(
                EntryInstrument.instrument_type
            ),
        )
    )
    entries_by_piece = defaultdict(list)
    for entry in _program_piece_filter(entries, program).all():
        entries_by_piece[entry.piece_id].append(entry)
    return entries_by_piece


def cover_sheets(program):
    """Return [(program_piece, [(entry, coming_from), ...], float_entries),
    ...]: every piece in program order, its ringers in roster order (P1-P11,
    then Other), and its Float ringers by first name. LB positions are left
    out; they get their own cover sheets (bass_bell_cover_sheets).

    coming_from is empty unless the program has a Starting placement report.
    Then it lists the bells, bell trees and percussion the ringer needs that
    are waiting at another position, as [(position, [(instrument_type,
    [item, ...]), ...]), ...] (see _coming_from).
    """
    order = {code: i for i, code in enumerate(ROSTER_POSITION_ORDER)}
    entries_by_piece = _program_entries_by_piece(program)
    coming_from = (
        _coming_from(program, entries_by_piece) if program.starting_placement else {}
    )

    result = []
    for program_piece in program.program_pieces:
        piece_entries = entries_by_piece[program_piece.piece_id]
        ringers = sorted(
            (
                e
                for e in piece_entries
                if e.position != FLOAT_POSITION
                and not e.position.startswith(BASS_POSITION_PREFIX)
            ),
            key=lambda e: (
                order.get(e.position, len(order)),
                e.position,
                e.user.first_name.casefold(),
            ),
        )
        floats = sorted(
            (e for e in piece_entries if e.position == FLOAT_POSITION),
            key=lambda e: e.user.first_name.casefold(),
        )
        result.append(
            (
                program_piece,
                [(e, coming_from.get(e.id, [])) for e in ringers],
                floats,
            )
        )
    return result


ALREADY_HERE = "Already here"
FROM_FLOOR = "Coming from Floor"


def _pitch_selections(entry):
    """The entry's pitch-mode selections that have pitches, in form order."""
    return [
        s
        for s in entry.sorted_instrument_selections()
        if s.instrument_type.selection_mode == "pitch" and s.note_list()
    ]


def bass_bell_cover_sheets(program):
    """Return [(program_piece, [(entry, bells, sources, other_selections), ...]),
    ...]: every piece in program order and its LB entries by position, then
    first name.

    bells are all of the entry's pitch-mode bells, as
    [(instrument_type, [pitch, ...]), ...], types in display order and
    pitches low to high.

    sources says where each of the entry's pitch-mode bells is waiting when
    the piece starts, as [(label, [(instrument_type, [pitch, ...]), ...]), ...].
    A bell stays with the position that last used it, even through pieces
    where nobody (or no one at that position) rings it, so it is wherever it
    was last used earlier in the program. The label is "Already here" when
    that is this position, "Coming from <position>" when it is another
    position (LB or not), and "Coming from Floor" when no earlier piece used
    it. Labels run Already here, then positions in roster order, then Floor;
    types in display order and pitches low to high. When several positions
    last used a bell on the same piece, this position wins, then the first
    in roster order.

    In a program with a Starting placement report, bells on it start at
    their starting placement position instead of the Floor; Bass Bells and
    Bass Chimes still come from the Floor.

    other_selections are the entry's non-pitch selections (mallets,
    percussion, sticks), in form order.
    """
    order = {code: i for i, code in enumerate(ROSTER_POSITION_ORDER)}

    def position_key(position):
        return (order.get(position, len(order)), position)

    entries_by_piece = _program_entries_by_piece(program)
    result = []
    # {(instrument_type_id, pitch): {position, ...}}: who last used each bell.
    bell_locations = {}
    if program.starting_placement:
        locations = _starting_locations(program, entries_by_piece)
        for entries in entries_by_piece.values():
            for entry in entries:
                for selection in entry.sorted_instrument_selections():
                    for key, instrument_type, item in _tracked_items(selection):
                        if instrument_type.selection_mode == "pitch":
                            bell_locations[(instrument_type.id, item)] = {
                                locations[key]
                            }
    for program_piece in program.program_pieces:
        piece_entries = entries_by_piece[program_piece.piece_id]

        rows = []
        lb_entries = sorted(
            (e for e in piece_entries if e.position.startswith(BASS_POSITION_PREFIX)),
            key=lambda e: (e.position, e.user.first_name.casefold()),
        )
        for entry in lb_entries:
            # {label: {instrument_type: [pitch, ...]}}
            grouped = defaultdict(lambda: defaultdict(list))
            for selection in _pitch_selections(entry):
                instrument_type = selection.instrument_type
                for p in selection.note_list():
                    holders = bell_locations.get((instrument_type.id, p), set())
                    if entry.position in holders:
                        label = ALREADY_HERE
                    elif holders:
                        label = f"Coming from {min(holders, key=position_key)}"
                    else:
                        label = FROM_FLOOR
                    grouped[label][instrument_type].append(p)

            def label_key(label):
                if label == ALREADY_HERE:
                    return (0, ())
                if label == FROM_FLOOR:
                    return (2, ())
                return (1, position_key(label.removeprefix("Coming from ")))

            sources = [
                (
                    label,
                    [
                        (instrument_type, sorted(pitches, key=pitch.pitch_index))
                        for instrument_type, pitches in sorted(
                            grouped[label].items(),
                            key=lambda item: (item[0].display_order, item[0].name),
                        )
                    ],
                )
                for label in sorted(grouped, key=label_key)
            ]
            bells = [
                (s.instrument_type, sorted(s.note_list(), key=pitch.pitch_index))
                for s in _pitch_selections(entry)
            ]
            other_selections = [
                s
                for s in entry.sorted_instrument_selections()
                if s.instrument_type.selection_mode != "pitch"
            ]
            rows.append((entry, bells, sources, other_selections))
        result.append((program_piece, rows))

        # Bells rung on this piece end up with whoever rang them; the rest
        # stay put.
        used_here = defaultdict(set)
        for entry in piece_entries:
            for selection in _pitch_selections(entry):
                for p in selection.note_list():
                    used_here[(selection.instrument_type_id, p)].add(entry.position)
        bell_locations.update(used_here)
    return result


def checkbox_max_counts(program):
    """Return {instrument_type: count} for checkbox-mode types (singing bell
    sticks): the most ringers who ticked it on any one piece in the program,
    which is how many to bring. Types in display order; a type nobody ticked
    is left out.
    """
    counts = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "checkbox":
            counts[instrument_type][entry_instrument.entry.piece_id] += 1
    return {
        instrument_type: max(counts[instrument_type].values())
        for instrument_type in sorted(counts, key=lambda t: (t.display_order, t.name))
    }


def used_options(program):
    """Return {instrument_type: [option, ...]} for options-mode types
    (percussion): every option picked at least once in the program. Types
    in display order, options in the type's order.
    """
    picked = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "options":
            picked[instrument_type].update(entry_instrument.selected_options())
    result = {}
    for instrument_type in sorted(picked, key=lambda t: (t.display_order, t.name)):
        options = [o for o in instrument_type.options if o in picked[instrument_type]]
        if options:
            result[instrument_type] = options
    return result


# Pitches from D7 up share a section with the pitch an octave below, so E7
# sits with E6 under E6/F6 and C8 with C7 under B6/C7.
EQUIPMENT_TABLE_FOLD_FROM = "D7"
# Pitches above this stay in their cases and are left off the table.
EQUIPMENT_TABLE_HIGHEST = "C8"


# Bell trees are set up on their own, so the equipment table lists them in a
# section of their own instead of under the pitch sections.
def _equipment_table_sections():
    """[(label, lowest pitch index), ...] low to high: one section per treble
    position, named by its notes ("C4/D4") and running up to the next
    position's first note, so C4/D4 holds C4, C#4, D4 and D#4. Pitches below
    the first position go in "Bass Equipment"."""
    trebles = [
        ("/".join(notes), pitch.pitch_index(notes[0]))
        for notes in POSITION_BASE_NOTES.values()
    ]
    trebles.sort(key=lambda section: section[1])
    return [("Bass Equipment", -1)] + trebles


def equipment_by_pitch(program):
    """Return [(label, [(instrument_type, [pitch, ...]), ...]), ...]: every
    pitch-mode instrument used anywhere in the program, sorted into the
    equipment table's pitch sections (see _equipment_table_sections), no
    matter which position rings it. Pitches from D7 to C8 go in the section
    of the pitch an octave below; higher ones are left out. Main Bells and
    Bass Bells (always set out) and non-pitch types are left out, as are
    empty sections, so Bass Equipment lists only extras like bass chimes.
    Bell trees are left out too; bell_trees() lists them. Types in display order, pitches low to high.
    """
    sections = _equipment_table_sections()
    lows = [low for _, low in sections]
    fold_from = pitch.pitch_index(EQUIPMENT_TABLE_FOLD_FROM)
    highest = pitch.pitch_index(EQUIPMENT_TABLE_HIGHEST)
    grouped = defaultdict(lambda: defaultdict(set))
    for entry_instrument in _entry_instruments_for_program(program):
        instrument_type = entry_instrument.instrument_type
        if (
            instrument_type.selection_mode != "pitch"
            or instrument_type.name in EQUIPMENT_LIST_EXCLUDED_TYPES
            or instrument_type.keyboard_type
        ):
            continue
        for p in entry_instrument.note_list():
            index = pitch.pitch_index(p)
            if index > highest:
                continue
            if index >= fold_from:
                index -= 12
            section = bisect_right(lows, index) - 1
            grouped[section][instrument_type].add(p)

    return [
        (
            sections[i][0],
            [
                (instrument_type, sorted(notes, key=pitch.pitch_index))
                for instrument_type, notes in sorted(
                    grouped[i].items(),
                    key=lambda item: (item[0].display_order, item[0].name),
                )
            ],
        )
        for i in sorted(grouped)
    ]


def bell_trees(program):
    """Return [(instrument_type, [pitch, ...]), ...]: every pitch used on
    each keyboard type (bell trees) anywhere in the program. Types in display order,
    pitches low to high; a tree nobody signed up for is left out."""
    pitches = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.keyboard_type and instrument_type.selection_mode == "pitch":
            pitches[instrument_type].update(entry_instrument.note_list())
    return [
        (instrument_type, sorted(notes, key=pitch.pitch_index))
        for instrument_type, notes in sorted(
            pitches.items(), key=lambda item: (item[0].display_order, item[0].name)
        )
        if notes
    ]


def misc_entries(program):
    """Entries in this program with non-blank misc notes, for attribution."""
    return [
        entry
        for entry in _program_piece_filter(Entry.query.join(Piece), program)
        if entry.misc_notes and entry.misc_notes.strip()
    ]


def mallet_max_counts(program):
    """Return [(label, count), ...]: for each kind of mallet, the most needed
    on any one piece (every ringer's count on that piece added up), which is
    how many to bring. Fixed colors in their usual order, then any "Other"
    mallets by name; a kind nobody signed up for is left out."""
    per_piece = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program):
        if entry_instrument.instrument_type.selection_mode != "color":
            continue
        piece_id = entry_instrument.entry.piece_id
        for label, count in entry_instrument.color_counts():
            per_piece[label][piece_id] += count
    order = {label: i for i, label in enumerate(color.MALLET_COLORS)}
    return [
        (label, max(per_piece[label].values()))
        for label in sorted(
            per_piece, key=lambda label: (order.get(label, len(order)), label)
        )
    ]


def progress_grid(cycle):
    """Who has entered equipment, laid out like the roster spreadsheet.

    Returns (pieces, rows, counts): pieces are the cycle's pieces in title
    order (the columns); rows are (position, [[entry, ...] per piece]) in
    roster order, with any position not on the roster sheet at the end;
    counts are {piece_id: (entered, expected)}. Float ringers don't enter
    equipment, so they aren't counted.
    """
    pieces = list(cycle.pieces)
    column = {piece.id: i for i, piece in enumerate(pieces)}
    entries = (
        Entry.query.join(Piece)
        .filter(Piece.cycle_id == cycle.id)
        .options(joinedload(Entry.user), selectinload(Entry.instrument_selections))
        .all()
    )

    cells = defaultdict(lambda: [[] for _ in pieces])
    counts = {piece.id: [0, 0] for piece in pieces}
    for entry in entries:
        cells[entry.position][column[entry.piece_id]].append(entry)
        if entry.position != FLOAT_POSITION:
            counts[entry.piece_id][1] += 1
            if entry.has_equipment():
                counts[entry.piece_id][0] += 1

    for row in cells.values():
        for cell in row:
            cell.sort(key=lambda e: e.user.first_name.casefold())
    positions = ROSTER_POSITION_ORDER + sorted(
        set(cells) - set(ROSTER_POSITION_ORDER)
    )
    rows = [
        (position, cells[position] if position in cells else [[] for _ in pieces])
        for position in positions
    ]
    return pieces, rows, {pid: tuple(c) for pid, c in counts.items()}


# Starting placement leaves out the bells always set out at their own spots.
STARTING_PLACEMENT_EXCLUDED_TYPES = {MAIN_BELLS, BASS_BELLS, BASS_CHIMES}
# The trebles low to high, then everyone else.
STARTING_PLACEMENT_ORDER = list(POSITION_BASE_NOTES) + [
    "LB3",
    "LB2",
    "LB1",
    "Other",
    FLOAT_POSITION,
]
_PLACEMENT_INDEX = {code: i for i, code in enumerate(STARTING_PLACEMENT_ORDER)}


def _placement_key(position):
    return (_PLACEMENT_INDEX.get(position, len(_PLACEMENT_INDEX)), position)


def _type_key(instrument_type):
    return (instrument_type.display_order, instrument_type.name)


def _tracked_items(selection, excluded=STARTING_PLACEMENT_EXCLUDED_TYPES):
    """Yield (key, instrument_type, item) for each single item `selection`
    uses that starting placement sets out and that then moves with whoever
    rings it: each pitch, a keyboard type (bell tree) as one item whatever
    pitches are used on it, and each percussion option. Items are pitches or
    option names. Mallets, singing bell sticks and the `excluded` types (by
    name) yield nothing.
    """
    instrument_type = selection.instrument_type
    if instrument_type.name in excluded:
        return
    if instrument_type.selection_mode == "pitch":
        for p in selection.note_list():
            if instrument_type.keyboard_type:
                yield (instrument_type.id, "tree"), instrument_type, p
            else:
                yield (instrument_type.id, p), instrument_type, p
    elif instrument_type.selection_mode == "options":
        for option in selection.selected_options():
            yield (instrument_type.id, option.id), instrument_type, option.name


def _sorted_items(instrument_type, items):
    """Pitches low to high, options in the type's order, without repeats;
    anything else as given."""
    if instrument_type.selection_mode == "pitch":
        return sorted(set(items), key=pitch.pitch_index)
    if instrument_type.selection_mode == "options":
        order = [o.name for o in instrument_type.options]
        return sorted(
            set(items), key=lambda name: order.index(name) if name in order else len(order)
        )
    return items


def _first_locations(
    program_pieces, entries_by_piece, excluded=STARTING_PLACEMENT_EXCLUDED_TYPES
):
    """{item key: position} for every tracked item (see _tracked_items) used
    on `program_pieces`: the position that first uses it in program order,
    the lowest in STARTING_PLACEMENT_ORDER when several first use it on the
    same piece."""
    locations = {}
    for program_piece in program_pieces:
        for entry in sorted(
            entries_by_piece[program_piece.piece_id],
            key=lambda e: _placement_key(e.position),
        ):
            for selection in entry.sorted_instrument_selections():
                for key, _, _ in _tracked_items(selection, excluded):
                    locations.setdefault(key, entry.position)
    return locations


def _starting_locations(program, entries_by_piece):
    """_first_locations over the whole program."""
    return _first_locations(program.program_pieces, entries_by_piece)


def _coming_from(program, entries_by_piece):
    """{entry id: [(position, [(instrument_type, [item, ...]), ...]), ...]}:
    for each entry, the tracked items it uses that are waiting at another
    position when its piece starts, grouped by that position.

    Items start at their starting placement position and stay with the
    position that last used them. When several positions last used an item
    on the same piece, the entry's own position wins, then the first in
    placement order. Positions in placement order, types in display order.
    """
    holders = {
        key: {position}
        for key, position in _starting_locations(program, entries_by_piece).items()
    }
    result = {}
    for program_piece in program.program_pieces:
        entries = entries_by_piece[program_piece.piece_id]
        for entry in entries:
            # {source position: {instrument_type: [item, ...]}}
            grouped = defaultdict(lambda: defaultdict(list))
            for selection in entry.sorted_instrument_selections():
                for key, instrument_type, item in _tracked_items(selection):
                    here = holders.get(key, set())
                    if here and entry.position not in here:
                        source = min(here, key=_placement_key)
                        grouped[source][instrument_type].append(item)
            result[entry.id] = [
                (
                    source,
                    [
                        (instrument_type, _sorted_items(instrument_type, items))
                        for instrument_type, items in sorted(
                            grouped[source].items(), key=lambda kv: _type_key(kv[0])
                        )
                    ],
                )
                for source in sorted(grouped, key=_placement_key)
            ]
        # Items rung on this piece end up with whoever rang them.
        used_here = defaultdict(set)
        for entry in entries:
            for selection in entry.sorted_instrument_selections():
                for key, _, _ in _tracked_items(selection):
                    used_here[key].add(entry.position)
        holders.update(used_here)
    return result


def starting_placement(program):
    """Return [(position_label, [(instrument_type, [item, ...]), ...]), ...]:
    where each piece of equipment is set out before the program starts,
    which is the position that first uses it in program order.

    Positions run P1-P11, then LB3-LB1, Other and Float, leaving out any
    with nothing to set out; types are in display order. Items are text:

    - Each pitch of a pitch-mode type, low to high. A pitch first used by
      several positions on the same piece goes to the first of them.
    - A keyboard type (bell tree) goes whole to the first position using
      any of its pitches, with every pitch used anywhere in the program.
    - Percussion options, like pitches, go to the first position to use them.
    - Mallets ("Red yarn ×2", with a non-breaking space) and singing bell
      sticks (no items; the type's form label says it) are counted, so
      every position using them on the piece where they're first used gets
      its own.

    Main Bells, Bass Bells and Bass Chimes are left out, as are misc notes.
    """
    entries_by_piece = _program_entries_by_piece(program)
    locations = _starting_locations(program, entries_by_piece)
    # {position: {instrument_type: [item, ...]}}
    placed = defaultdict(lambda: defaultdict(list))
    seen = set()  # counted items first used on an earlier piece
    for program_piece in program.program_pieces:
        counted_here = set()
        for entry in entries_by_piece[program_piece.piece_id]:
            position = entry.position
            for selection in entry.sorted_instrument_selections():
                # Single items go wherever they start, whoever uses them.
                for key, instrument_type, item in _tracked_items(selection):
                    placed[locations[key]][instrument_type].append(item)
                instrument_type = selection.instrument_type
                if instrument_type.selection_mode == "checkbox":
                    key = (instrument_type.id,)
                    if key not in seen:
                        counted_here.add(key)
                        placed[position][instrument_type]  # listed by name; no items
                elif instrument_type.selection_mode == "color":
                    for label, count in selection.color_counts():
                        key = (instrument_type.id, label)
                        if key not in seen:
                            counted_here.add(key)
                            placed[position][instrument_type].append(
                                # Non-breaking, so "×2" never wraps alone.
                                f"{label}\u00a0×{count}"
                            )
        seen |= counted_here

    return [
        (
            position_label(position),
            [
                (instrument_type, _sorted_items(instrument_type, items))
                for instrument_type, items in sorted(
                    placed[position].items(), key=lambda kv: _type_key(kv[0])
                )
            ],
        )
        for position in sorted(placed, key=_placement_key)
    ]


# --- sets and resets -------------------------------------------------------

# Main Bells are always out; everything else is set out and put away at the
# Resets between sets.
RESET_EXCLUDED_TYPES = {MAIN_BELLS}


class _SetSummary:
    """What one set of a program uses, for working out its Resets.

    - first: {item key: position} where each single item (see
      _tracked_items) is first used in the set - where it's put out.
    - last: {item key: position} the position holding each single item at
      the end of the set - who takes it off. That's the last position to
      ring it, the lowest in placement order when several do on the same
      piece.
    - items: {item key: (instrument_type, [item, ...])} the item's text; a
      bell tree's lists every pitch used on it in the set.
    - need: {position: {(instrument_type, label): count}} for counted items,
      the most of each kind the position uses on any one piece of the set.
      label is the mallet color, or None for singing bell sticks (count 1).
    """

    def __init__(self, program_pieces=(), entries_by_piece=None):
        self.program_pieces = list(program_pieces)
        self.first = (
            _first_locations(self.program_pieces, entries_by_piece, RESET_EXCLUDED_TYPES)
            if self.program_pieces
            else {}
        )
        self.last = {}
        self.items = {}
        self.need = defaultdict(dict)
        for program_piece in self.program_pieces:
            used_here = defaultdict(set)
            for entry in entries_by_piece[program_piece.piece_id]:
                position = entry.position
                for selection in entry.sorted_instrument_selections():
                    for key, instrument_type, item in _tracked_items(
                        selection, RESET_EXCLUDED_TYPES
                    ):
                        used_here[key].add(position)
                        self.items.setdefault(key, (instrument_type, []))[1].append(item)
                    instrument_type = selection.instrument_type
                    if instrument_type.name in RESET_EXCLUDED_TYPES:
                        continue
                    if instrument_type.selection_mode == "checkbox":
                        kinds = [((instrument_type, None), 1)]
                    elif instrument_type.selection_mode == "color":
                        kinds = [
                            ((instrument_type, label), count)
                            for label, count in selection.color_counts()
                        ]
                    else:
                        kinds = []
                    for kind, count in kinds:
                        need = self.need[position]
                        need[kind] = max(need.get(kind, 0), count)
            for key, positions in used_here.items():
                self.last[key] = min(positions, key=_placement_key)

    def changes(self, other, locations):
        """What this set uses that `other` doesn't, as
        [(position, [(instrument_type, [item, ...]), ...]), ...]: single
        items at their position in `locations` (self.first or self.last),
        and counted items by how many more this set needs at each position.
        Positions in placement order, types in display order.
        """
        placed = defaultdict(lambda: defaultdict(list))
        for key, (instrument_type, items) in self.items.items():
            if key not in other.items:
                placed[locations[key]][instrument_type].extend(items)
        mallet_order = {label: i for i, label in enumerate(color.MALLET_COLORS)}
        for position, kinds in self.need.items():
            other_need = other.need.get(position, {})
            for (instrument_type, label), count in sorted(
                kinds.items(),
                key=lambda kv: (
                    mallet_order.get(kv[0][1], len(mallet_order)),
                    kv[0][1] or "",
                ),
            ):
                extra = count - other_need.get((instrument_type, label), 0)
                if extra <= 0:
                    continue
                if label is None:
                    placed[position][instrument_type]  # listed by name; no items
                else:
                    # Non-breaking, so "×2" never wraps alone.
                    placed[position][instrument_type].append(f"{label}\u00a0×{extra}")
        return _by_position(placed)

    def carry(self, following, type_ids):
        """Leave this set's single items of the instrument types in
        `type_ids` on the table for `following`, the next set, where it
        doesn't use them itself. They stay with the position holding them
        at the end of this set, which takes them off at the end of
        `following` (unless they're carried again). Return what's left on,
        as changes() does."""
        placed = defaultdict(lambda: defaultdict(list))
        for key, (instrument_type, items) in self.items.items():
            if instrument_type.id in type_ids and key not in following.items:
                following.items[key] = (instrument_type, items)
                following.last[key] = self.last[key]
                placed[self.last[key]][instrument_type].extend(items)
        return _by_position(placed)


def _by_position(placed):
    """{position: {instrument_type: [item, ...]}} as [(position,
    [(instrument_type, [item, ...]), ...]), ...], positions in placement
    order and types in display order."""
    return [
        (
            position,
            [
                (instrument_type, _sorted_items(instrument_type, items))
                for instrument_type, items in sorted(
                    placed[position].items(), key=lambda kv: _type_key(kv[0])
                )
            ],
        )
        for position in sorted(placed, key=_placement_key)
    ]


class Reset:
    """One changeover in a program with sets: before the first set, or
    between two sets.

    - title: "Before Set 1" or "Reset between Sets 1 and 2".
    - ended: the program pieces of the set just finished (empty before the
      first set), whose last piece decides who takes off what.
    - started: the program pieces of the set about to start, whose first
      piece decides who puts out what.
    - take_off, put_out, leave_on: [(position, [(instrument_type, [item,
      ...]), ...]), ...] by position code, in placement order. leave_on is
      what the finished set's last ringers leave on the table for the next
      set (ProgramKeepOut) rather than taking off.
    """

    def __init__(self, title, ended, started, take_off, put_out, leave_on=()):
        self.title = title
        self.ended = ended
        self.started = started
        self.take_off = take_off
        self.put_out = put_out
        self.leave_on = list(leave_on)

    @property
    def ended_set_number(self):
        """The finished set's number, or None before the first set."""
        return self.ended[0].set_number if self.ended else None

    @property
    def started_set_number(self):
        return self.started[0].set_number

    @property
    def ended_piece(self):
        """The finished set's last piece, whose ringers take off; None
        before the first set."""
        return self.ended[-1].piece if self.ended else None

    @property
    def started_piece(self):
        """The next set's first piece, whose ringers put out."""
        return self.started[0].piece

    def by_position(self):
        """[(position, take_off, put_out, leave_on), ...]: each position
        with anything to do, in placement order, and its three lists of
        [(instrument_type, [item, ...]), ...]."""
        take_off, put_out = dict(self.take_off), dict(self.put_out)
        leave_on = dict(self.leave_on)
        return [
            (
                position,
                take_off.get(position, []),
                put_out.get(position, []),
                leave_on.get(position, []),
            )
            for position in sorted(
                {*take_off, *put_out, *leave_on}, key=_placement_key
            )
        ]


def resets(program, entries_by_piece=None):
    """Return [Reset, ...]: what to put out before the first set, then at
    each Reset what to take off at the end of the set just finished and put
    out for the next. Nothing after the last set; everything goes away then.
    Empty for a program without sets.

    Single items (each pitch, a bell tree as one item, each percussion
    option) are put out where they're first used in the set, unless the set
    before also used them, so they're already out. They're taken off at the
    end of a set by the position holding them then - the last to ring them -
    unless the next set uses them too. Mallets and singing bell sticks are
    counted per position: a position puts out however many more of each
    kind it needs than it had in the set before, and takes off however many
    more it had than it needs in the next. Main Bells are left out.

    The program's keep-outs (ProgramKeepOut) leave an instrument type's
    single items on the table at the Reset after a set, for the next set:
    the position holding them takes them off a Reset later instead. Each
    Reset's leave_on lists them. Counted items aren't carried.
    """
    sets = program.sets()
    if not sets:
        return []
    if entries_by_piece is None:
        entries_by_piece = _program_entries_by_piece(program)
    summaries = [_SetSummary(pieces, entries_by_piece) for pieces in sets]
    keep_outs = defaultdict(set)  # {set number: {instrument type id, ...}}
    for keep_out in program.keep_outs:
        keep_outs[keep_out.after_set].add(keep_out.instrument_type_id)
    # In set order, so items carried into a set can be carried again.
    leave_on = [[]] + [
        previous.carry(current, keep_outs[pieces[0].set_number])
        for previous, current, pieces in zip(summaries, summaries[1:], sets)
    ]
    result = []
    for i, current in enumerate(summaries):
        number = sets[i][0].set_number
        if i == 0:
            result.append(
                Reset(
                    f"Before Set {number}",
                    [],
                    current.program_pieces,
                    [],
                    current.changes(_SetSummary(), current.first),
                )
            )
            continue
        previous = summaries[i - 1]
        result.append(
            Reset(
                f"Reset between Sets {sets[i - 1][0].set_number} and {number}",
                previous.program_pieces,
                current.program_pieces,
                previous.changes(current, previous.last),
                current.changes(previous, current.first),
                leave_on[i],
            )
        )
    return result


def _position_on(program_piece, entries):
    """The user's position on `program_piece`, or None if they aren't on it."""
    if program_piece is None:
        return None
    entry = entries.get(program_piece.piece_id)
    return entry.position if entry is not None else None


def my_resets(program, user):
    """Return [(reset, end_position, take_off, leave_on, start_position,
    put_out), ...]: one row per Reset (see resets), for one ringer.

    end_position is where they finish the set just ended, take_off what
    that position takes off and leave_on what it leaves on the table for
    the next set; start_position is where they start the next set
    and put_out what that position puts out. The two are looked up apart,
    since a ringer can come back from a Reset at a different position.
    Equipment belongs to the position, so whoever is there takes it off or
    puts it out. take_off, leave_on and put_out are [(instrument_type,
    [item, ...]), ...].

    Only whoever starts a set puts out and only whoever finishes it takes
    off: start_position is the ringer's position on the next set's first
    piece and end_position on the finished set's last piece. Either is None
    (and its list empty) when they aren't on that piece, since someone else
    sees to it then; end_position is also None before the first set.
    leave_on is empty whenever end_position is None.
    """
    entries_by_piece = _program_entries_by_piece(program)
    return _my_reset_rows(user.id, resets(program, entries_by_piece), entries_by_piece)


def _my_reset_rows(user_id, program_resets, entries_by_piece):
    """my_resets for one user, from already-worked-out resets."""
    mine = {
        piece_id: entry
        for piece_id, entries in entries_by_piece.items()
        for entry in entries
        if entry.user_id == user_id
    }
    result = []
    for reset in program_resets:
        end_position = _position_on(reset.ended[-1] if reset.ended else None, mine)
        start_position = _position_on(reset.started[0], mine)
        result.append(
            (
                reset,
                end_position,
                dict(reset.take_off).get(end_position, []),
                dict(reset.leave_on).get(end_position, []),
                start_position,
                dict(reset.put_out).get(start_position, []),
            )
        )
    return result


def everyones_resets(program):
    """Return [(user, my_resets rows), ...] for everyone assigned to a piece
    in the program, by name, for printing each ringer's page."""
    entries_by_piece = _program_entries_by_piece(program)
    program_resets = resets(program, entries_by_piece)
    users = {
        entry.user.id: entry.user
        for entries in entries_by_piece.values()
        for entry in entries
    }
    return [
        (user, _my_reset_rows(user.id, program_resets, entries_by_piece))
        for user in sorted(users.values(), key=lambda u: (u.name.casefold(), u.id))
    ]


# --- equipment conflicts ---------------------------------------------------

# There are enough Main Bells and Bass Bells for every position to have its
# own, so only other instruments can be claimed twice.
CONFLICT_EXCLUDED_TYPES = {MAIN_BELLS, BASS_BELLS}


def equipment_conflicts(cycle):
    """Return [(piece, [(instrument_type, item, [entry, ...]), ...]), ...]:
    each piece in the cycle (by title) where more than one position signed
    up for the same instrument, which can't be in two places at once.

    An instrument is a single item as in _tracked_items: each pitch, each
    percussion option, or a whole bell tree (whose item is then its name),
    leaving out Main Bells and Bass Bells. Mallets and singing bell sticks
    are counted, not single instruments, so they never conflict. Items are
    in display order, pitches low to high and options in the type's order;
    each item's entries are in placement order.
    """
    entries = (
        Entry.query.join(Piece)
        .filter(Piece.cycle_id == cycle.id)
        .options(
            joinedload(Entry.user),
            selectinload(Entry.instrument_selections).joinedload(
                EntryInstrument.instrument_type
            ),
        )
        .all()
    )
    # {piece_id: {item key: {entry id: entry}}}
    claims = defaultdict(lambda: defaultdict(dict))
    # {item key: (instrument_type, item text, sort value)}
    items = {}
    for entry in entries:
        for selection in entry.sorted_instrument_selections():
            for key, instrument_type, item in _tracked_items(
                selection, CONFLICT_EXCLUDED_TYPES
            ):
                claims[entry.piece_id][key][entry.id] = entry
                if instrument_type.keyboard_type:
                    items[key] = (instrument_type, instrument_type.name, -1)
                elif instrument_type.selection_mode == "pitch":
                    items[key] = (instrument_type, item, pitch.pitch_index(item))
                else:
                    option_ids = [o.id for o in instrument_type.options]
                    items[key] = (instrument_type, item, option_ids.index(key[1]))

    result = []
    for piece in cycle.pieces:
        conflicts = [
            (
                items[key],
                sorted(
                    claimants.values(),
                    key=lambda e: (_placement_key(e.position), e.user.first_name.casefold()),
                ),
            )
            for key, claimants in claims[piece.id].items()
            if len(claimants) > 1
        ]
        if conflicts:
            conflicts.sort(key=lambda c: (_type_key(c[0][0]), c[0][2]))
            result.append(
                (
                    piece,
                    [
                        (instrument_type, item, claimants)
                        for (instrument_type, item, _), claimants in conflicts
                    ],
                )
            )
    return result
