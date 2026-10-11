"""Load cases from a CSV (seed/cases.csv) via `flask load-cases`.

Columns: case, type, low, high, second_low, second_high. ``type`` names an
existing instrument type. A blank ``high`` means the case holds a single bell,
so it's stored as low-low; the second range is optional.

Each row overwrites the case with the same case number, or adds it if it's
new. Cases not in the sheet are left alone. Every row is checked before
anything is written, so a sheet with any problem loads nothing.
"""

import csv
import io
from dataclasses import dataclass, field

from app import db, pitch
from app.models import Case, InstrumentType

COLUMNS = ["case", "type", "low", "high", "second_low", "second_high"]
VALID_PITCHES = set(pitch.all_pitches())


@dataclass
class LoadResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize(text):
    return " ".join((text or "").split()).casefold()


def load_cases(csv_text, dry_run=False):
    """Add or overwrite cases from ``csv_text``; commits unless ``dry_run``."""
    result = LoadResult()
    reader = csv.DictReader(io.StringIO(csv_text))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        result.errors.append(f"Missing column(s): {', '.join(missing)}.")
        return result

    types_by_name = {_normalize(t.name): t for t in InstrumentType.query.all()}
    existing = {c.case_number: c for c in Case.query.all()}
    seen = set()

    with db.session.no_autoflush:
        # Line 1 is the header row.
        for line, row in enumerate(reader, start=2):
            values = {c: (row.get(c) or "").strip() for c in COLUMNS}
            if not any(values.values()):
                continue
            number = values["case"]
            label = f"Line {line} ({number or 'no case number'})"
            if not number:
                result.errors.append(f"{label}: missing case number.")
                continue
            if number in seen:
                result.errors.append(f"{label}: case number appears more than once.")
                continue
            seen.add(number)

            instrument_type = types_by_name.get(_normalize(values["type"]))
            if instrument_type is None:
                result.errors.append(
                    f"{label}: no instrument type named {values['type']!r}."
                )
                continue
            if not values["low"]:
                result.errors.append(f"{label}: missing low note.")
                continue
            notes = {
                "note_range_low": values["low"],
                "note_range_high": values["high"] or values["low"],
                "second_range_low": values["second_low"] or None,
                "second_range_high": values["second_high"] or None,
            }
            bad = [n for n in notes.values() if n and n not in VALID_PITCHES]
            if bad:
                result.errors.append(f"{label}: unknown pitch {', '.join(bad)}.")
                continue

            case = existing.get(number)
            if case is None:
                case = Case(case_number=number)
                db.session.add(case)
                result.added.append(number)
            else:
                result.updated.append(number)
            case.instrument_type = instrument_type
            for column, value in notes.items():
                setattr(case, column, value)
            error = case.validation_error()
            if error:
                result.errors.append(f"{label}: {error}")

    if result.errors or dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return result
