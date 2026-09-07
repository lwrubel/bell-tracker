from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import color, db, reports
from app.forms import (
    build_equipment_form,
    color_field_name,
    instrument_field_name,
    other_count_field_name,
    other_label_field_name,
)
from app.models import Concert, Entry, EntryInstrument, Piece
from app.positions import FLOAT_POSITION

bp = Blueprint("routes", __name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@bp.route("/")
def index():
    return redirect(url_for("routes.concerts_index"))


@bp.route("/concerts")
@login_required
def concerts_index():
    concerts = Concert.query.order_by(Concert.date.desc()).all()
    return render_template("concerts.html", concerts=concerts)


@bp.route("/concerts/<int:concert_id>")
@login_required
def concert_detail(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    entries_by_piece = {
        entry.piece_id: entry
        for entry in Entry.query.join(Piece)
        .filter(Piece.concert_id == concert_id, Entry.user_id == current_user.id)
        .all()
    }
    pieces = [p for p in concert.pieces if p.id in entries_by_piece]
    return render_template(
        "concert_detail.html",
        concert=concert,
        pieces=pieces,
        entries_by_piece=entries_by_piece,
        float_position=FLOAT_POSITION,
        mallet_requirements_by_piece=reports.mallet_requirements(concert),
    )


@bp.route(
    "/concerts/<int:concert_id>/pieces/<int:piece_id>/entry", methods=["GET", "POST"]
)
@login_required
def piece_entry(concert_id, piece_id):
    concert = Concert.query.get_or_404(concert_id)
    piece = Piece.query.filter_by(id=piece_id, concert_id=concert_id).first_or_404()
    entry = Entry.query.filter_by(user_id=current_user.id, piece_id=piece_id).first()
    if entry is None or entry.position == FLOAT_POSITION:
        abort(404)

    # Position-restricted types (bass bells for LB positions) drop out here,
    # and this same list drives the save loop below - so a ringer moved off
    # LB won't have their stored bass bells wiped on their next save.
    visible_types = entry.visible_instrument_types()

    existing_by_type = {
        sel.instrument_type_id: sel for sel in entry.instrument_selections
    }
    initial = {"misc_notes": entry.misc_notes or ""}
    for t in visible_types:
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
        else:
            initial[instrument_field_name(t.id)] = (
                selection.note_list() if selection else []
            )

    is_post = request.method == "POST"
    form = build_equipment_form(
        entry,
        formdata=request.form if is_post else None,
        data=None if is_post else initial,
    )

    if form.validate_on_submit():
        entry.misc_notes = form.misc_notes.data
        existing_selections = {
            sel.instrument_type_id: sel for sel in entry.instrument_selections
        }
        for instrument_type in visible_types:
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
        flash("Saved.", "success")
        return redirect(url_for("routes.concert_detail", concert_id=concert_id))

    mallet_totals = reports.mallet_requirements(concert).get(piece.id)
    return render_template(
        "piece_entry.html",
        concert=concert,
        piece=piece,
        entry=entry,
        form=form,
        instrument_types=visible_types,
        mallet_totals=mallet_totals,
    )


def _selected_notes_value(form, instrument_type):
    """The string to store in EntryInstrument.notes for one instrument type,
    from the submitted form (pitch list or color:count pairs)."""
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
    return ",".join(field.data or [])


@bp.route("/concerts/<int:concert_id>/reports/packing-list")
@admin_required
def report_packing_list(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    cases_by_type = reports.packing_list(concert)
    return render_template(
        "packing_list.html", concert=concert, cases_by_type=cases_by_type
    )


@bp.route("/concerts/<int:concert_id>/reports/equipment-table")
@admin_required
def report_equipment_table(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    notes_by_type, mallet_counts_by_type, misc_entries = reports.equipment_table(
        concert
    )
    return render_template(
        "equipment_table.html",
        concert=concert,
        notes_by_type=notes_by_type,
        mallet_counts_by_type=mallet_counts_by_type,
        mallet_requirements_by_piece=reports.mallet_requirements(concert),
        misc_entries=misc_entries,
    )
