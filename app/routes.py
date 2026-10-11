from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app import color, db, reports
from app.forms import (
    build_equipment_form,
    color_field_name,
    instrument_field_name,
    other_count_field_name,
    other_label_field_name,
)
from app.models import CHECKED_NOTES, Cycle, Entry, EntryInstrument, Piece, Program
from app.positions import FLOAT_POSITION

bp = Blueprint("routes", __name__)


def reports_required(view):
    """Admins and managers only."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_view_reports:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@bp.route("/")
@login_required
def index():
    return render_template("home.html", cycle=Cycle.get_active())


def _my_entries_by_piece(piece_filter):
    """The current user's entries on pieces matching `piece_filter`, keyed
    by piece id."""
    return {
        entry.piece_id: entry
        for entry in Entry.query.join(Piece)
        .filter(piece_filter, Entry.user_id == current_user.id)
        .options(
            selectinload(Entry.instrument_selections).joinedload(
                EntryInstrument.instrument_type
            )
        )
        .all()
    }


@bp.route("/cycles/<int:cycle_id>")
@login_required
def cycle_detail(cycle_id):
    cycle = Cycle.query.get_or_404(cycle_id)
    entries_by_piece = _my_entries_by_piece(Piece.cycle_id == cycle_id)
    pieces = [p for p in cycle.pieces if p.id in entries_by_piece]
    return render_template(
        "cycle_detail.html",
        cycle=cycle,
        pieces=pieces,
        entries_by_piece=entries_by_piece,
        float_position=FLOAT_POSITION,
    )


@bp.route("/programs/<int:program_id>/my-equipment")
@login_required
def my_equipment(program_id):
    program = Program.query.get_or_404(program_id)
    entries_by_piece = _my_entries_by_piece(
        Piece.id.in_([pp.piece_id for pp in program.program_pieces])
    )
    program_entries = [
        (pp.position, entries_by_piece[pp.piece_id])
        for pp in program.program_pieces
        if pp.piece_id in entries_by_piece
    ]
    return render_template(
        "my_equipment.html", program=program, program_entries=program_entries
    )


@bp.route("/pieces/<int:piece_id>/entry", methods=["GET", "POST"])
@login_required
def piece_entry(piece_id):
    piece = Piece.query.get_or_404(piece_id)
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
        elif t.selection_mode == "checkbox":
            initial[instrument_field_name(t.id)] = selection is not None
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
        return redirect(url_for("routes.cycle_detail", cycle_id=piece.cycle_id))

    return render_template(
        "piece_entry.html",
        piece=piece,
        entry=entry,
        form=form,
        instrument_types=visible_types,
    )


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


def _include_special():
    """Reports include special pieces unless the admin asks to leave them out."""
    return request.args.get("special") != "exclude"


@bp.route("/programs/<int:program_id>/reports/cases-list")
@reports_required
def report_cases_list(program_id):
    program = Program.query.get_or_404(program_id)
    include_special = _include_special()
    return render_template(
        "cases_list.html",
        program=program,
        include_special=include_special,
        special_pieces=[p for p in program.pieces if p.special],
        cases_by_type=reports.cases_list(program, include_special),
    )


@bp.route("/programs/<int:program_id>/reports/equipment-pull-list")
@reports_required
def report_equipment_pull_list(program_id):
    program = Program.query.get_or_404(program_id)
    include_special = _include_special()
    return render_template(
        "equipment_pull_list.html",
        program=program,
        include_special=include_special,
        special_pieces=[p for p in program.pieces if p.special],
        bells_by_type=reports.equipment_pull_list(program, include_special),
        checkbox_counts=reports.checkbox_max_counts(program, include_special),
        used_options=reports.used_options(program, include_special),
    )


@bp.route("/programs/<int:program_id>/reports/bass-bells")
@reports_required
def report_bass_bells(program_id):
    program = Program.query.get_or_404(program_id)
    include_special = _include_special()
    return render_template(
        "bass_bells.html",
        program=program,
        include_special=include_special,
        special_pieces=[p for p in program.pieces if p.special],
        pieces=reports.bass_bells(program, include_special),
    )


@bp.route("/programs/<int:program_id>/reports/equipment-table")
@reports_required
def report_equipment_table(program_id):
    program = Program.query.get_or_404(program_id)
    include_special = _include_special()
    notes_by_type, mallet_counts_by_type, misc_entries = reports.equipment_table(
        program, include_special
    )
    return render_template(
        "equipment_table.html",
        program=program,
        include_special=include_special,
        special_pieces=[p for p in program.pieces if p.special],
        notes_by_type=notes_by_type,
        mallet_counts_by_type=mallet_counts_by_type,
        checkbox_counts=reports.checkbox_max_counts(program, include_special),
        used_options=reports.used_options(program, include_special),
        mallet_requirements_by_piece=reports.mallet_requirements(
            program, include_special
        ),
        misc_entries=misc_entries,
    )
