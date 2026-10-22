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
from app.positions import FLOAT_POSITION, ROSTER_POSITION_ORDER


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


# Instrument types left out of the equipment pull list, by name.
EQUIPMENT_PULL_LIST_EXCLUDED_TYPES = {MAIN_BELLS, BASS_BELLS}


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
        if instrument_type.name in EQUIPMENT_PULL_LIST_EXCLUDED_TYPES:
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


def equipment_table(program):
    """Return (notes_by_type, mallet_counts_by_type, misc_entries) for laying
    equipment out for this program.

    notes_by_type: {instrument_type: [pitch, ...]} sorted low to high (pitch-mode
        types other than Main Bells, which are always on the tables).
    mallet_counts_by_type: {instrument_type: {label: total_count}} (color-mode types).
    misc_entries: Entry rows with non-empty misc_notes, for attribution.
    """
    notes_by_type = defaultdict(set)
    mallet_counts_by_type = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "color":
            for label, count in entry_instrument.color_counts():
                mallet_counts_by_type[instrument_type][label] += count
        elif (
            instrument_type.selection_mode == "pitch"
            and instrument_type.name != MAIN_BELLS
        ):
            notes_by_type[instrument_type].update(entry_instrument.note_list())

    sorted_notes_by_type = {
        instrument_type: sorted(notes, key=pitch.pitch_index)
        for instrument_type, notes in notes_by_type.items()
        if notes
    }
    mallet_counts_by_type = {
        instrument_type: dict(counts)
        for instrument_type, counts in mallet_counts_by_type.items()
        if counts
    }

    misc_entries = [
        entry
        for entry in _program_piece_filter(Entry.query.join(Piece), program)
        if entry.misc_notes and entry.misc_notes.strip()
    ]

    return sorted_notes_by_type, mallet_counts_by_type, misc_entries


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
