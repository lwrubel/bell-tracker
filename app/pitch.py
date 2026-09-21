"""Fixed chromatic pitch reference shared by forms, admin, and reports.

Scientific pitch notation is a universal fact, not admin-editable data,
so it lives here as a constant rather than a database table.
"""

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Flat spellings, index-aligned with NOTE_NAMES, for display only. Pitches are
# always stored/keyed using the sharp names above; this is purely a rendering
# option for users who prefer flat notation.
FLAT_NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

LOWEST_PITCH = "F2"
HIGHEST_PITCH = "C9"


def pitch_index(name: str) -> int:
    """Return a comparable integer index for a pitch name, e.g. "C4" -> 48."""
    octave = int(name[-1])
    note = name[:-1]
    return octave * 12 + NOTE_NAMES.index(note)


def flat_name(name: str) -> str:
    """Return the flat spelling of a (sharp-stored) pitch name, e.g. "C#4" -> "Db4"."""
    octave = int(name[-1])
    note = name[:-1]
    return f"{FLAT_NOTE_NAMES[NOTE_NAMES.index(note)]}{octave}"


def all_pitches(low: str = LOWEST_PITCH, high: str = HIGHEST_PITCH) -> list[str]:
    """Return the ordered chromatic pitch names from low to high, inclusive."""
    low_index = pitch_index(low)
    high_index = pitch_index(high)
    pitches = []
    for index in range(low_index, high_index + 1):
        octave, note_offset = divmod(index, 12)
        pitches.append(f"{NOTE_NAMES[note_offset]}{octave}")
    return pitches


def pitches_in_range(low: str, high: str) -> list[str]:
    return all_pitches(low, high)


def in_range(name: str, low: str, high: str) -> bool:
    return pitch_index(low) <= pitch_index(name) <= pitch_index(high)
