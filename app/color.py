"""Fixed mallet color vocabulary shared by forms, admin, and reports.

Mallet colors are a fixed manufacturer vocabulary, not admin-editable
data, so they live here as a constant rather than a database table (same
reasoning as ``app/pitch.py``).

Color-mode instrument selections are stored in ``EntryInstrument.notes`` as
a comma-separated list of ``label:count`` pairs, e.g.
``"Green yarn:2,Red yarn:1,Other: soft bass:1"``. ``format_color_counts``
and ``parse_color_counts`` are the encode/decode pair.
"""

MALLET_COLORS = [
    "Black yarn",
    "Red yarn",
    "Gray yarn",
    "Blue yarn",
    "Blue hard",
    "Black hard",
    "Brown hard",
    "White hard",
    "Green yarn",
    "Bass red yarn",
    "Bass forest green yarn",
]

# Prefix for the free-text "Other" row a ringer can add alongside the fixed
# colors. The text after the prefix is the ringer's own description.
OTHER_PREFIX = "Other: "


def sanitize_label(text: str) -> str:
    """Strip the characters used as delimiters in the stored encoding so a
    free-text "Other" description can't corrupt it."""
    return (text or "").replace(":", " ").replace(",", " ").strip()


def format_color_counts(items) -> str:
    """Encode ``[(label, count), ...]`` as ``"label:count,label:count"``,
    dropping any entry whose count is missing or not positive."""
    parts = []
    for label, count in items:
        try:
            count = int(count)
        except (TypeError, ValueError):
            continue
        if label and count > 0:
            parts.append(f"{label}:{count}")
    return ",".join(parts)


def parse_color_counts(notes: str):
    """Inverse of :func:`format_color_counts`. Malformed, zero, and
    non-integer chunks are skipped."""
    result = []
    for chunk in (notes or "").split(","):
        chunk = chunk.strip()
        if ":" not in chunk:
            continue
        label, _, raw = chunk.rpartition(":")
        label = label.strip()
        try:
            count = int(raw)
        except ValueError:
            continue
        if label and count > 0:
            result.append((label, count))
    return result
