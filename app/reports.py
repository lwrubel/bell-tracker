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
    """Return (notes_by_type, misc_entries) for laying equipment out for this concert.

    notes_by_type: {instrument_type: [pitch, ...]} sorted low to high.
    misc_entries: Entry rows with non-empty misc_notes, for attribution.
    """
    notes_by_type = defaultdict(set)
    for entry_instrument in _entry_instruments_for_concert(concert):
        notes_by_type[entry_instrument.instrument_type].update(
            entry_instrument.note_list()
        )

    sorted_notes_by_type = {
        instrument_type: sorted(notes, key=pitch.pitch_index)
        for instrument_type, notes in notes_by_type.items()
        if notes
    }

    misc_entries = [
        entry
        for entry in Entry.query.join(Piece).filter(Piece.concert_id == concert.id)
        if entry.misc_notes and entry.misc_notes.strip()
    ]

    return sorted_notes_by_type, misc_entries
