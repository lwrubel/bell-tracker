"""Fixed ringing-position codes, admin-assigned per (user, piece)."""

POSITION_CODES = [f"P{i}" for i in range(1, 12)] + ["LB1", "LB2", "LB3", "Float", "Other"]

FLOAT_POSITION = "Float"

# The two base notes each treble position rings. Positions not listed here
# (LB, Float, Other) have no fixed notes and display as their bare code.
POSITION_BASE_NOTES = {
    "P1": ("C4", "D4"),
    "P2": ("E4", "F4"),
    "P3": ("G4", "A4"),
    "P4": ("B4", "C5"),
    "P5": ("D5", "E5"),
    "P6": ("F5", "G5"),
    "P7": ("A5", "B5"),
    "P8": ("C6", "D6"),
    "P9": ("E6", "F6"),
    "P10": ("G6", "A6"),
    "P11": ("B6", "C7"),
}


def position_label(code):
    """Display text for a position, e.g. "P1" -> "P1 - C4/D4", "LB1" -> "LB1"."""
    notes = POSITION_BASE_NOTES.get(code)
    return f"{code} - {'/'.join(notes)}" if notes else code


def position_prefixes():
    """Distinct alphabetic prefixes of the position codes: P, LB, Float, Other.

    Derived rather than hardcoded so an InstrumentType's position_prefix can
    only ever be set to something the codes above actually start with.
    """
    prefixes = []
    for code in POSITION_CODES:
        prefix = code.rstrip("0123456789")
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes
