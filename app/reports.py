from collections import defaultdict

from app import pitch
from app.models import Entry, EntryInstrument, Piece


def _entry_instruments_for_concert(concert):
    return (
        EntryInstrument.query.join(Entry)
        .join(Piece)
        .filter(Piece.concert_id == concert.id)
        .all()
    )


def packing_list(concert):
    """Return {instrument_type: [case, ...]} for cases whose note range
    overlaps a pitch actually used somewhere in this concert."""
    used_pitches_by_type = defaultdict(set)
    for entry_instrument in _entry_instruments_for_concert(concert):
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
            if any(
                pitch.in_range(p, case.note_range_low, case.note_range_high)
                for p in used_pitches
            )
        ]
        if needed_cases:
            result[instrument_type] = sorted(needed_cases, key=lambda c: c.case_number)
    return result


def equipment_table(concert):
    """Return (notes_by_type, mallet_counts_by_type, misc_entries) for laying
    equipment out for this concert.

    notes_by_type: {instrument_type: [pitch, ...]} sorted low to high (pitch-mode types).
    mallet_counts_by_type: {instrument_type: {label: total_count}} (color-mode types).
    misc_entries: Entry rows with non-empty misc_notes, for attribution.
    """
    notes_by_type = defaultdict(set)
    mallet_counts_by_type = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_concert(concert):
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
        for entry in Entry.query.join(Piece).filter(Piece.concert_id == concert.id)
        if entry.misc_notes and entry.misc_notes.strip()
    ]

    return sorted_notes_by_type, mallet_counts_by_type, misc_entries


def mallet_requirements(concert):
    """Return {piece_id: {label: total_count}} — mallet colors needed per
    piece, summed across every ringer's entry for that piece."""
    result = defaultdict(lambda: defaultdict(int))
    for entry_instrument in _entry_instruments_for_concert(concert):
        if entry_instrument.instrument_type.selection_mode != "color":
            continue
        piece_id = entry_instrument.entry.piece_id
        for label, count in entry_instrument.color_counts():
            result[piece_id][label] += count
    return {piece_id: dict(counts) for piece_id, counts in result.items()}
