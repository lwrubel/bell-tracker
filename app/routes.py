from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app import db, reports
from app.equipment import equipment_form_for, save_equipment
from app.models import (
    BASS_BELLS,
    Cycle,
    Entry,
    EntryInstrument,
    Piece,
    Program,
    ProgramPiece,
)
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


def _bass_program_ids(user, programs):
    """Ids of the programs, out of `programs`, where `user` rings an LB
    position on at least one piece."""
    program_ids = [program.id for program in programs]
    if not program_ids:
        return set()
    rows = (
        db.session.query(ProgramPiece.program_id)
        .join(Entry, Entry.piece_id == ProgramPiece.piece_id)
        .filter(
            Entry.user_id == user.id,
            Entry.position.startswith(reports.BASS_POSITION_PREFIX),
            ProgramPiece.program_id.in_(program_ids),
        )
        .distinct()
    )
    return {program_id for (program_id,) in rows}


@bp.route("/")
@login_required
def index():
    cycle = Cycle.get_active()
    return render_template(
        "home.html",
        cycle=cycle,
        bass_program_ids=_bass_program_ids(current_user, cycle.programs if cycle else []),
    )


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


@bp.route("/programs/<int:program_id>/order")
@login_required
def program_order(program_id):
    """The whole program's pieces in performance order, for everyone -
    including admins who aren't assigned to any of them."""
    program = Program.query.get_or_404(program_id)
    return render_template("program_order.html", program=program)


@bp.route("/pieces/<int:piece_id>/entry", methods=["GET", "POST"])
@login_required
def piece_entry(piece_id):
    piece = Piece.query.get_or_404(piece_id)
    entry = Entry.query.filter_by(user_id=current_user.id, piece_id=piece_id).first()
    if entry is None or entry.position == FLOAT_POSITION:
        abort(404)

    form = equipment_form_for(
        entry, formdata=request.form if request.method == "POST" else None
    )
    if form.validate_on_submit():
        save_equipment(entry, form)
        flash("Saved.", "success")
        return redirect(url_for("routes.cycle_detail", cycle_id=piece.cycle_id))

    return render_template(
        "piece_entry.html",
        piece=piece,
        entry=entry,
        form=form,
        instrument_types=entry.visible_instrument_types(),
    )


@bp.route("/programs/<int:program_id>/reports/cases-list")
@reports_required
def report_cases_list(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template(
        "cases_list.html",
        program=program,
        cases_by_type=reports.cases_list(program),
    )


@bp.route("/programs/<int:program_id>/reports/equipment-pull-list")
@reports_required
def report_equipment_pull_list(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template(
        "equipment_pull_list.html",
        program=program,
        bells_by_type=reports.equipment_pull_list(program),
        checkbox_counts=reports.checkbox_max_counts(program),
        used_options=reports.used_options(program),
    )


@bp.route("/programs/<int:program_id>/reports/bass-bells")
@reports_required
def report_bass_bells(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template(
        "bass_bells.html",
        program=program,
        pieces=reports.bass_bells(program),
    )


@bp.route("/programs/<int:program_id>/reports/cover-sheets")
@login_required
def report_cover_sheets(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template(
        "cover_sheets.html",
        program=program,
        pieces=reports.cover_sheets(program),
    )


@bp.route("/programs/<int:program_id>/reports/bass-bell-cover-sheets")
@login_required
def report_bass_bell_cover_sheets(program_id):
    """Admins, managers, and anyone ringing an LB position in the program."""
    program = Program.query.get_or_404(program_id)
    if not (
        current_user.can_view_reports
        or program.id in _bass_program_ids(current_user, [program])
    ):
        abort(403)
    return render_template(
        "bass_bell_cover_sheets.html",
        program=program,
        BASS_BELLS=BASS_BELLS,
        pieces=reports.bass_bell_cover_sheets(program),
    )


@bp.route("/programs/<int:program_id>/reports/equipment-table")
@reports_required
def report_equipment_table(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template(
        "equipment_table.html",
        program=program,
        sections=reports.equipment_by_pitch(program),
        checkbox_counts=reports.checkbox_max_counts(program),
        used_options=reports.used_options(program),
        mallet_requirements_by_piece=reports.mallet_requirements(program),
        misc_entries=reports.misc_entries(program),
    )
