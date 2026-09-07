"""Fixed ringing-position codes, admin-assigned per (user, piece)."""

POSITION_CODES = [f"P{i}" for i in range(1, 12)] + ["LB1", "LB2", "LB3", "Float", "Aux"]

FLOAT_POSITION = "Float"


def position_prefixes():
    """Distinct alphabetic prefixes of the position codes: P, LB, Float, Aux.

    Derived rather than hardcoded so an InstrumentType's position_prefix can
    only ever be set to something the codes above actually start with.
    """
    prefixes = []
    for code in POSITION_CODES:
        prefix = code.rstrip("0123456789")
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes
