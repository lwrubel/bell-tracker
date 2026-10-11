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


def cases_list(program, include_special=True):
    """Return {instrument_type: [case, ...]} for cases whose note range
    overlaps a pitch actually used somewhere in this program."""
    used_pitches_by_type = defaultdict(set)
    for entry_instrument in _entry_instruments_for_program(program, include_special):
        if entry_instrument.instrument_type.selection_mode == "color":
            continue  # color-mode types have no pitch cases
        used_pitches_by_type[entry_instrument.instrument_type].update(
            entry_instrument.note_list()
        )

    result = {}
    for instrument_type, used_pitches in used_pitches_by_type.items():
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
        else:
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
