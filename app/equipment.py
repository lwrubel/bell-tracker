"""Loading and saving an entry's equipment form.

Shared by the ringer's own piece entry page and the admin's equipment page
for an entry, so both read and write EntryInstrument rows the same way.
"""

from app import color, db
from app.forms import (
    build_equipment_form,
    color_field_name,
    instrument_field_name,
    other_count_field_name,
    other_label_field_name,
)
from app.models import CHECKED_NOTES, EntryInstrument


def equipment_form_for(entry, formdata=None):
    """The equipment form for `entry`: bound to `formdata` when it's a
    submission, otherwise prefilled from what's stored."""
    return build_equipment_form(
        entry,
        formdata=formdata,
        data=None if formdata is not None else _initial_data(entry),
    )


def _initial_data(entry):
    existing_by_type = {
        sel.instrument_type_id: sel for sel in entry.instrument_selections
    }
    initial = {"misc_notes": entry.misc_notes or ""}
    for t in entry.visible_instrument_types():
        selection = existing_by_type.get(t.id)
        if t.selection_mode == "color":
            counts = dict(selection.color_counts()) if selection else {}
            for i, color_name in enumerate(color.MALLET_COLORS):
                initial[color_field_name(t.id, i)] = counts.pop(color_name, 0)
            other_label, other_count = "", 0
            for label, count in counts.items():
                other_count = count
                other_label = (
                    label[len(color.OTHER_PREFIX):]
                    if label.startswith(color.OTHER_PREFIX)
                    else label
                )
                break
            initial[other_label_field_name(t.id)] = other_label
            initial[other_count_field_name(t.id)] = other_count
        elif t.selection_mode == "checkbox":
            initial[instrument_field_name(t.id)] = selection is not None
        else:
            initial[instrument_field_name(t.id)] = (
                selection.note_list() if selection else []
            )
    return initial


def save_equipment(entry, form):
    """Store a validated equipment form on `entry` and commit.

    Only the entry's visible instrument types are touched, so a ringer moved
    off LB won't have their stored bass bells wiped on the next save.
    """
    entry.misc_notes = form.misc_notes.data
    existing_selections = {
        sel.instrument_type_id: sel for sel in entry.instrument_selections
    }
    for instrument_type in entry.visible_instrument_types():
        notes_value = _selected_notes_value(form, instrument_type)
        selection = existing_selections.get(instrument_type.id)
        if notes_value:
            if selection is None:
                selection = EntryInstrument(
                    entry=entry, instrument_type_id=instrument_type.id
                )
                db.session.add(selection)
            selection.notes = notes_value
        elif selection is not None:
            db.session.delete(selection)
    db.session.commit()


def _selected_notes_value(form, instrument_type):
    """The string to store in EntryInstrument.notes for one instrument type,
    from the submitted form (pitch list, color:count pairs, a tick, or
    option ids)."""
    if instrument_type.selection_mode == "color":
        items = [
            (color_name, getattr(form, color_field_name(instrument_type.id, i)).data)
            for i, color_name in enumerate(color.MALLET_COLORS)
        ]
        other_label = (
            getattr(form, other_label_field_name(instrument_type.id)).data or ""
        ).strip()
        other_count = getattr(form, other_count_field_name(instrument_type.id)).data
        if other_label and other_count:
            items.append(
                (color.OTHER_PREFIX + color.sanitize_label(other_label), other_count)
            )
        return color.format_color_counts(items)
    field = getattr(form, instrument_field_name(instrument_type.id))
    if instrument_type.selection_mode == "checkbox":
        return CHECKED_NOTES if field.data else ""
    return ",".join(field.data or [])
