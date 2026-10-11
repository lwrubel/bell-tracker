from collections import defaultdict

from app import pitch
from app.models import Entry, EntryInstrument, Piece, ProgramPiece


def _program_piece_filter(query, program, include_special):
    query = query.join(ProgramPiece, ProgramPiece.piece_id == Piece.id).filter(
        ProgramPiece.program_id == program.id
    )
    if not include_special:
        query = query.filter(Piece.special.is_(False))
    return query


def _entry_instruments_for_program(program, include_special=True):
    query = EntryInstrument.query.join(Entry).join(Piece)
    return _program_piece_filter(query, program, include_special).all()


def _used_pitches_by_type(program, include_special):
    """{instrument_type: {pitch, ...}} for pitch-mode types signed up in
    this program."""
    used_pitches_by_type = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        if entry_instrument.instrument_type.selection_mode != "pitch":
            continue  # only pitch-mode types have cases
        used_pitches_by_type[entry_instrument.instrument_type].update(
            entry_instrument.note_list()
        )
    return used_pitches_by_type


def cases_list(program, include_special=True):
    """Return {instrument_type: [case, ...]} for cases whose note range
    overlaps a pitch actually used somewhere in this program."""
    result = {}
    for instrument_type, used_pitches in _used_pitches_by_type(
        program, include_special
    ).items():
        if not used_pitches:
            continue
        needed_cases = [
            case
            for case in instrument_type.cases
            if any(case.covers(p) for p in used_pitches)
        ]
        if needed_cases:
            result[instrument_type] = sorted(needed_cases, key=lambda c: c.case_number)
    return result


# Instrument types left out of the equipment pull list, by name.
EQUIPMENT_PULL_LIST_EXCLUDED_TYPES = {"Main Bells", "Bass Bells"}


def equipment_pull_list(program, include_special=True):
    """Return {instrument_type: ([(case, [pitch, ...]), ...], [pitch, ...])}:
    for each type, the bells to take out of each case, then any used pitches
    no case covers. Types are in display order, cases by number, pitches low
    to high. Main Bells and Bass Bells are left out.

    A pitch covered by two cases is listed under both, matching the cases
    used list, which brings both.
    """
    result = {}
    used_pitches_by_type = _used_pitches_by_type(program, include_special)
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
        for case in sorted(instrument_type.cases, key=lambda c: c.case_number):
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


def bass_bells(program, include_special=True):
    """Return [(program_piece, [(entry, bells), ...]), ...]: every piece in
    program order, each LB entry on it by position, and the bells that
    position signed up for as [(instrument_type, [pitch, ...]), ...], types
    in display order and pitches low to high. A piece with no LB positions
    has an empty list.
    """
    result = []
    for program_piece in program.program_pieces:
        piece = program_piece.piece
        if not include_special and piece.special:
            continue
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


def checkbox_max_counts(program, include_special=True):
    """Return {instrument_type: count} for checkbox-mode types (singing bell
    sticks): the most ringers who ticked it on any one piece in the program,
    which is how many to bring. Types in display order; a type nobody ticked
    is left out.
    """
    counts = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "checkbox":
            counts[instrument_type][entry_instrument.entry.piece_id] += 1
    return {
        instrument_type: max(counts[instrument_type].values())
        for instrument_type in sorted(counts, key=lambda t: (t.display_order, t.name))
    }


def used_options(program, include_special=True):
    """Return {instrument_type: [option, ...]} for options-mode types
    (percussion): every option picked at least once in the program. Types
    in display order, options in the type's order.
    """
    picked = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "options":
            picked[instrument_type].update(entry_instrument.selected_options())
    result = {}
    for instrument_type in sorted(picked, key=lambda t: (t.display_order, t.name)):
        options = [o for o in instrument_type.options if o in picked[instrument_type]]
        if options:
            result[instrument_type] = options
    return result


def equipment_table(program, include_special=True):
    """Return (notes_by_type, mallet_counts_by_type, misc_entries) for laying
    equipment out for this program. With include_special=False, pieces the
    admin marked special are left out entirely.

    notes_by_type: {instrument_type: [pitch, ...]} sorted low to high (pitch-mode types).
    mallet_counts_by_type: {instrument_type: {label: total_count}} (color-mode types).
    misc_entries: Entry rows with non-empty misc_notes, for attribution.
    """
    notes_by_type = defaultdict(set)
    mallet_counts_by_type = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        instrument_type = entry_instrument.instrument_type
        if instrument_type.selection_mode == "color":
            for label, count in entry_instrument.color_counts():
                mallet_counts_by_type[instrument_type][label] += count
        elif instrument_type.selection_mode == "pitch":
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
        for entry in _program_piece_filter(
            Entry.query.join(Piece), program, include_special
        )
        if entry.misc_notes and entry.misc_notes.strip()
    ]

    return sorted_notes_by_type, mallet_counts_by_type, misc_entries


def mallet_requirements(program, include_special=True):
    """Return {piece_id: {label: total_count}} — mallet colors needed per
    piece, summed across every ringer's entry for that piece."""
    result = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        if entry_instrument.instrument_type.selection_mode != "color":
            continue
        piece_id = entry_instrument.entry.piece_id
        for label, count in entry_instrument.color_counts():
            result[piece_id][label] += count
    return {piece_id: dict(counts) for piece_id, counts in result.items()}
