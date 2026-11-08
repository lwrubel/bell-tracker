from bisect import bisect_right
from collections import defaultdict

from sqlalchemy.orm import joinedload, selectinload

from app import pitch
from app.models import (
    ALWAYS_LISTED_CASE_TYPES,
    BASS_BELLS,
    MAIN_BELLS,
    Case,
    Entry,
    EntryInstrument,
    InstrumentType,
    Piece,
    ProgramPiece,
)
from app.positions import FLOAT_POSITION, POSITION_BASE_NOTES, ROSTER_POSITION_ORDER


def _program_piece_filter(query, program):
    return query.join(ProgramPiece, ProgramPiece.piece_id == Piece.id).filter(
        ProgramPiece.program_id == program.id
    )


def _entry_instruments_for_program(program):
    query = EntryInstrument.query.join(Entry).join(Piece)
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
    """Return [(program_piece, entries, float_entries), ...]: every piece in
    program order, its ringers in roster order (P1-P11, then Other), and its
    Float ringers by first name. LB positions are left out; they get their
    own cover sheets (bass_bell_cover_sheets).
    """
    order = {code: i for i, code in enumerate(ROSTER_POSITION_ORDER)}
    entries_by_piece = _program_entries_by_piece(program)

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
        result.append((program_piece, ringers, floats))
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
    empty sections, so Bass Equipment lists only extras like bass chimes. Types in display order, pitches low to high.
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


def misc_entries(program):
    """Entries in this program with non-blank misc notes, for attribution."""
    return [
        entry
        for entry in _program_piece_filter(Entry.query.join(Piece), program)
        if entry.misc_notes and entry.misc_notes.strip()
    ]


def mallet_requirements(program):
    """Return {piece_id: {label: total_count}} — mallet colors needed per
    piece, summed across every ringer's entry for that piece."""
    result = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program):
        if entry_instrument.instrument_type.selection_mode != "color":
            continue
        piece_id = entry_instrument.entry.piece_id
        for label, count in entry_instrument.color_counts():
            result[piece_id][label] += count
    return {piece_id: dict(counts) for piece_id, counts in result.items()}


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
