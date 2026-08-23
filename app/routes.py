from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, reports
from app.forms import build_equipment_form, instrument_field_name
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

    existing_by_type = {
        sel.instrument_type_id: sel.note_list() for sel in entry.instrument_selections
    }
    initial = {
        instrument_field_name(t.id): existing_by_type.get(t.id, [])
        for t in piece.instrument_types
    }
    initial["misc_notes"] = entry.misc_notes or ""

    is_post = request.method == "POST"
    form = build_equipment_form(
        piece,
        formdata=request.form if is_post else None,
        data=None if is_post else initial,
    )

    if form.validate_on_submit():
        entry.misc_notes = form.misc_notes.data
        existing_selections = {
            sel.instrument_type_id: sel for sel in entry.instrument_selections
        }
        for instrument_type in piece.instrument_types:
            field = getattr(form, instrument_field_name(instrument_type.id))
            selected_notes = field.data or []
            selection = existing_selections.get(instrument_type.id)
            if selected_notes:
                if selection is None:
                    selection = EntryInstrument(
                        entry=entry, instrument_type_id=instrument_type.id
                    )
                    db.session.add(selection)
                selection.notes = ",".join(selected_notes)
            elif selection is not None:
                db.session.delete(selection)
        db.session.commit()
        flash("Saved.", "success")
        return redirect(url_for("routes.concert_detail", concert_id=concert_id))

    return render_template(
        "piece_entry.html", concert=concert, piece=piece, entry=entry, form=form
    )


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
    notes_by_type, misc_entries = reports.equipment_table(concert)
    return render_template(
        "equipment_table.html",
        concert=concert,
        notes_by_type=notes_by_type,
        misc_entries=misc_entries,
    )
