from flask import abort, flash, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.helpers import get_redirect_target
from flask_admin.model.template import EndpointLinkRowAction
from flask_admin.theme import Bootstrap4Theme
from flask_login import current_user
from wtforms import PasswordField, SelectField

from app import color, db, pitch, reports, roster_import
from app.equipment import equipment_form_for, save_equipment
from app.models import (
    Case,
    Cycle,
    Entry,
    InstrumentOption,
    InstrumentType,
    Piece,
    Program,
    ProgramEarlyPutOut,
    ProgramKeepOut,
    ProgramPiece,
    User,
)
from app.positions import (
    FLOAT_POSITION,
    POSITION_CODES,
    position_label,
    position_prefixes,
)

PITCH_CHOICES = [(p, p) for p in pitch.all_pitches()]
# Range is optional for color-mode instrument types, so offer a blank choice.
OPTIONAL_PITCH_CHOICES = [("", "— none —")] + PITCH_CHOICES
POSITION_CHOICES = [(c, position_label(c)) for c in POSITION_CODES]
SELECTION_MODE_CHOICES = [
    ("pitch", "pitch"),
    ("color", "color"),
    ("checkbox", "checkbox"),
    ("options", "options"),
]
# Picking from the real prefixes means a typo can't silently disable the rule.
POSITION_PREFIX_CHOICES = [("", "— any position —")] + [
    (p, p) for p in position_prefixes()
]


class AdminAccessMixin:
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login", next=request.url))


class SecureModelView(AdminAccessMixin, ModelView):
    pass


class SecureAdminIndexView(AdminAccessMixin, AdminIndexView):
    pass


class UserAdminView(SecureModelView):
    column_list = ("email", "name", "first_name", "is_admin", "is_manager")
    form_columns = (
        "email",
        "name",
        "first_name",
        "is_admin",
        "is_manager",
        "password",
    )
    form_extra_fields = {"password": PasswordField("Password")}
    form_args = {
        "first_name": {
            "description": "The name used for this ringer in roster spreadsheets. "
            "Import positions matches on it, so each ringer's should be unique. "
            "Leave blank to use the first word of Name."
        },
        "is_manager": {
            "description": "Managers see every program's reports on the home "
            "page, but not the admin panel."
        },
    }

    def on_model_change(self, form, model, is_created):
        model.email = model.email.strip().lower()
        model.first_name = " ".join((model.first_name or "").split()) or (
            model.name.split() or [""]
        )[0]
        if form.password.data:
            model.set_password(form.password.data)
            # A password an admin chose is a temporary one - unless the admin
            # is setting their own.
            if model.id is None or model.id != current_user.id:
                model.must_change_password = True
        elif is_created:
            raise Exception("Password is required when creating a user.")


class CycleAdminView(SecureModelView):
    column_list = ("name", "active")
    form_columns = ("name", "active")
    form_args = {
        "active": {
            "description": "The cycle ringers see when they log in. Making this "
            "cycle active deactivates whichever one was."
        }
    }
    # "id" must stay in form_columns even though it's not user-editable:
    # Flask-Admin's inline-form machinery reads it to tell new rows from
    # existing ones when saving. Omitting it raises
    # AttributeError: 'ProgramForm' object has no attribute 'id'.
    inline_models = [(Program, {"form_columns": ["id", "name", "datetime"]})]


class ProgramAdminView(SecureModelView):
    column_list = ("cycle", "name", "datetime", "starting_placement")
    form_columns = ("cycle", "name", "datetime", "starting_placement")
    column_labels = {
        "datetime": "Date and time",
        "starting_placement": "Starting placement report",
    }
    form_args = {
        "starting_placement": {
            "label": "Starting placement report",
            "description": "Show the Starting placement report for this program.",
        }
    }
    # The pieces this program plays, numbered in program order. See
    # CycleAdminView for why "id" is listed.
    # "Position" means a ringer's spot in a piece everywhere else, so the
    # piece's place in the program is labelled "Order" here.
    inline_models = [
        (
            ProgramPiece,
            {
                "form_columns": [
                    "id",
                    "piece",
                    "position",
                    "set_number",
                    "cover_sheet",
                    "non_handbell",
                ],
                "form_args": {
                    "position": {"label": "Order"},
                    "cover_sheet": {
                        "label": "Cover sheet",
                        "description": "Untick for a piece that needs no cover "
                        "sheet; it's left off the Standard and Bass bells cover "
                        "sheets.",
                        "default": True,
                    },
                    "non_handbell": {
                        "label": "Non-handbell",
                        "description": "Tick for a piece not rung on handbells. "
                        "It stays in its set but doesn't decide who puts out or "
                        "takes off at a Reset.",
                    },
                    "set_number": {
                        "label": "Set",
                        "description": "For programs split into sets: 1, 2, ... "
                        "Number every piece or none.",
                    },
                },
            },
        ),
        # Instrument types left on the table at a Reset for one more set
        # (reports.resets).
        (
            ProgramKeepOut,
            {
                "form_columns": ["id", "instrument_type", "after_set"],
                "form_label": "Leave on table",
                "form_args": {
                    "instrument_type": {"label": "Leave on table"},
                    "after_set": {
                        "label": "After set",
                        "description": "Leave this instrument type on the "
                        "table at the Reset after this set, so it stays out "
                        "for one more set.",
                    },
                },
            },
        ),
        # Instrument types whose next-set items are put out a set early
        # (reports.resets).
        (
            ProgramEarlyPutOut,
            {
                "form_columns": ["id", "instrument_type", "before_set"],
                "form_label": "Put out early",
                "form_args": {
                    "instrument_type": {"label": "Put out early"},
                    "before_set": {
                        "label": "Before set",
                        "description": "Put out everything of this instrument "
                        "type that this set or the next one uses before this "
                        "set starts.",
                    },
                },
            },
        ),
    ]

    def on_model_change(self, form, model, is_created):
        for program_piece in model.program_pieces:
            piece = program_piece.piece
            if piece is not None and piece.cycle_id != model.cycle.id:
                raise Exception(
                    f'"{piece.title}" is in {piece.cycle.name}, not '
                    f"{model.cycle.name}; a program can only play its own "
                    "cycle's pieces."
                )
        _check_set_numbers(model.program_pieces)
        _check_keep_outs(model)


def _check_keep_outs(program):
    """Each keep-out and early put-out names one of the program's sets
    other than the last, since there's no next set to leave things out for
    or put things out early for."""
    numbers = sorted(
        {pp.set_number for pp in program.program_pieces if pp.set_number is not None}
    )
    checks = [
        (k.after_set, "leave things on the table after") for k in program.keep_outs
    ] + [
        (e.before_set, "put things out early before") for e in program.early_put_outs
    ]
    for number, action in checks:
        if number not in numbers[:-1]:
            if not numbers:
                problem = "this program has no sets"
            elif number == numbers[-1]:
                problem = f"Set {number} is the last set"
            else:
                problem = f"this program has no Set {number}"
            raise Exception(f"Can't {action} Set {number}: {problem}.")


def _check_set_numbers(program_pieces):
    """Every piece has a set number or none does, and they never go down in
    program order, so each set is one run of pieces (Program.sets)."""
    numbered = [pp.set_number is not None for pp in program_pieces]
    if not any(numbered):
        return
    if not all(numbered):
        raise Exception(
            "Give every piece a set number, or leave them all blank for a "
            "program without sets."
        )
    previous = None
    for program_piece in sorted(program_pieces, key=lambda pp: pp.position or 0):
        if previous is not None and program_piece.set_number < previous:
            raise Exception(
                "Set numbers must not go down in program order; each set's "
                "pieces should come together."
            )
        previous = program_piece.set_number


class PieceAdminView(SecureModelView):
    column_list = ("cycle", "title", "instrument_types")
    form_columns = ("cycle", "title", "instrument_types")


class InstrumentTypeAdminView(SecureModelView):
    column_default_sort = ("display_order", False)
    column_list = (
        "display_order",
        "name",
        "selection_mode",
        "note_range_low",
        "note_range_high",
        "position_prefix",
        "enabled_by_default",
        "keyboard_type",
    )
    form_columns = (
        "display_order",
        "name",
        "form_label",
        "selection_mode",
        "note_range_low",
        "note_range_high",
        "position_prefix",
        "enabled_by_default",
        "keyboard_type",
    )
    column_labels = {"keyboard_type": "Keyboard type"}
    form_overrides = {
        "selection_mode": SelectField,
        "note_range_low": SelectField,
        "note_range_high": SelectField,
        "position_prefix": SelectField,
    }
    form_args = {
        "selection_mode": {"choices": SELECTION_MODE_CHOICES},
        "note_range_low": {"choices": OPTIONAL_PITCH_CHOICES},
        "note_range_high": {"choices": OPTIONAL_PITCH_CHOICES},
        "position_prefix": {"choices": POSITION_PREFIX_CHOICES},
        "form_label": {
            "description": (
                "What ringers see on their equipment form. Leave blank to use "
                "the name."
            )
        },
        "keyboard_type": {
            "label": "Keyboard type",
            "description": (
                "Set up as one instrument with all its pitches together, like "
                "a bell tree. The Equipment Tables list its pitches in their "
                "own section instead of under each position's range."
            ),
        },
    }
    # What ringers can pick on an options-mode type (Percussion). See
    # CycleAdminView for why "id" is listed.
    inline_models = [(InstrumentOption, {"form_columns": ["id", "name"]})]

    def on_model_change(self, form, model, is_created):
        model.form_label = (model.form_label or "").strip() or None
        # "" from the blank choice means "no restriction", not a prefix.
        if not model.position_prefix:
            model.position_prefix = None
        if model.selection_mode != "pitch":
            # Color-mode types (mallets) pick from app/color.py and
            # checkbox-mode types are a single tick, not pitches.
            model.note_range_low = None
            model.note_range_high = None
            return
        if not model.note_range_low or not model.note_range_high:
            raise Exception(
                "Pitch-based instrument types need both a low and a high note."
            )
        if pitch.pitch_index(model.note_range_low) > pitch.pitch_index(
            model.note_range_high
        ):
            raise Exception("Low note must not be above the high note.")


class CaseAdminView(SecureModelView):
    column_list = (
        "case_number",
        "instrument_type",
        "note_range_low",
        "note_range_high",
        "second_range_low",
        "second_range_high",
    )
    form_columns = column_list
    form_overrides = {
        "note_range_low": SelectField,
        "note_range_high": SelectField,
        "second_range_low": SelectField,
        "second_range_high": SelectField,
    }
    form_args = {
        "note_range_low": {"choices": PITCH_CHOICES},
        "note_range_high": {"choices": PITCH_CHOICES},
        # Most cases hold a single run of bells, so the second is optional.
        "second_range_low": {"choices": OPTIONAL_PITCH_CHOICES},
        "second_range_high": {"choices": OPTIONAL_PITCH_CHOICES},
    }

    def on_model_change(self, form, model, is_created):
        # "" from the blank choice means "no second range".
        model.second_range_low = model.second_range_low or None
        model.second_range_high = model.second_range_high or None
        error = model.validation_error()
        if error:
            raise Exception(error)


def _format_instrument_selections(view, context, model, name):
    parts = []
    for sel in model.instrument_selections:
        instrument_type = sel.instrument_type
        if instrument_type.selection_mode == "color":
            body = ", ".join(
                f"{label} ×{count}" for label, count in sel.color_counts()
            )
        elif instrument_type.selection_mode == "checkbox":
            body = "Yes"
        elif instrument_type.selection_mode == "options":
            body = ", ".join(o.name for o in sel.selected_options())
        else:
            body = sel.notes or ""
        parts.append(f"{instrument_type.name}: {body}")
    return ", ".join(parts)


class EntryAdminView(SecureModelView):
    """Roster-assignment tool: admins assign user+piece+position here.

    Ringers fill in their own equipment from the front end; admins can
    correct or add to it - misc_notes on the edit form, instrument
    selections on the separate equipment page, which reuses the ringer's
    form so both store selections the same way.
    """

    column_list = ("user", "piece", "position", "misc_notes", "instrument_selections")
    column_details_list = (
        "user",
        "piece",
        "position",
        "misc_notes",
        "instrument_selections",
    )
    column_formatters = {
        "position": lambda view, context, model, name: position_label(model.position),
        "instrument_selections": _format_instrument_selections,
    }
    can_view_details = True
    # Look up one ringer's entries by any of the names they might go by.
    column_searchable_list = ("user.name", "user.first_name", "user.email", "piece.title")
    column_filters = ("user.name", "piece.title", "position")
    column_sortable_list = (("user", "user.name"), ("piece", "piece.title"), "position")
    column_default_sort = [("user.name", False), ("piece.title", False)]
    form_columns = ("user", "piece", "position", "misc_notes")
    form_overrides = {"position": SelectField}
    form_args = {"position": {"choices": POSITION_CHOICES}}
    edit_template = "admin/entry_edit.html"
    column_extra_row_actions = [
        EndpointLinkRowAction(
            "fa fa-music", ".equipment_view", title="Edit instrument selections"
        )
    ]

    @expose("/equipment/", methods=["GET", "POST"])
    def equipment_view(self):
        return_url = get_redirect_target() or self.get_url(".index_view")
        entry = self.get_one(request.args.get("id", ""))
        if entry is None:
            abort(404)

        form = equipment_form_for(
            entry, formdata=request.form if request.method == "POST" else None
        )
        if form.validate_on_submit():
            save_equipment(entry, form)
            flash(
                f"Saved equipment for {entry.user.name} on {entry.piece.title}.",
                "success",
            )
            return redirect(return_url)

        return self.render(
            "admin/entry_equipment.html",
            entry=entry,
            form=form,
            instrument_types=entry.visible_instrument_types(),
            return_url=return_url,
        )


# A roster sheet is a few KB; anything this big is the wrong file.
MAX_ROSTER_BYTES = 1024 * 1024


class RosterImportView(AdminAccessMixin, BaseView):
    """Upload a roster CSV, preview the assignments it makes, then confirm.

    The confirm step posts the CSV text back and re-plans it, so nothing is
    held server-side between the two requests and the preview can't go
    stale against the database.
    """

    @expose("/", methods=["GET", "POST"])
    def index(self):
        cycles = Cycle.query.order_by(Cycle.id.desc()).all()
        if request.method == "GET":
            return self.render("admin/roster_import.html", cycles=cycles)

        cycle = db.session.get(Cycle, request.form.get("cycle_id", type=int) or 0)
        if cycle is None:
            flash("Choose a cycle.", "danger")
            return redirect(url_for(".index"))

        if "confirm" in request.form:
            csv_text = request.form.get("csv_text", "")
        else:
            csv_text, error = _read_upload(request.files.get("file"))
            if error:
                flash(error, "danger")
                return redirect(url_for(".index"))

        plan = roster_import.plan_import(cycle, csv_text)
        if "confirm" in request.form and plan.can_apply:
            roster_import.apply_import(cycle, plan)
            flash(
                f"Imported positions into {cycle.name}: "
                f"{len(plan.new_piece_titles)} pieces created, "
                f"{plan.count(roster_import.ADD)} assignments added, "
                f"{plan.count(roster_import.UPDATE)} changed.",
                "success",
            )
            return redirect(url_for(".index"))

        return self.render(
            "admin/roster_import.html",
            cycles=cycles,
            cycle=cycle,
            plan=plan,
            csv_text=csv_text,
            actions=roster_import,
        )


def _read_upload(file):
    """Return (text, error) for an uploaded CSV."""
    if file is None or not file.filename:
        return None, "Choose a CSV file to upload."
    data = file.read(MAX_ROSTER_BYTES + 1)
    if len(data) > MAX_ROSTER_BYTES:
        return None, "That file is too large to be a roster sheet."
    try:
        # utf-8-sig drops the byte-order mark Excel puts on CSV exports.
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "Couldn't read that file. Save it as CSV (UTF-8) and try again."


class ProgressReportView(AdminAccessMixin, BaseView):
    """A cycle's assignments laid out like the roster spreadsheet, with a
    check by each ringer who has entered their equipment."""

    @expose("/")
    def index(self):
        cycles = Cycle.query.order_by(Cycle.id.desc()).all()
        cycle_id = request.args.get("cycle_id", type=int)
        cycle = (
            db.session.get(Cycle, cycle_id) if cycle_id else Cycle.get_active()
        ) or (cycles[0] if cycles else None)
        pieces, rows, counts = reports.progress_grid(cycle) if cycle else ([], [], {})
        return self.render(
            "admin/progress_report.html",
            cycles=cycles,
            cycle=cycle,
            pieces=pieces,
            rows=rows,
            counts=counts,
            float_position=FLOAT_POSITION,
        )


class EquipmentConflictsView(AdminAccessMixin, BaseView):
    """Pieces where two positions signed up for the same instrument, so
    an admin can sort it out with the ringers."""

    @expose("/")
    def index(self):
        cycles = Cycle.query.order_by(Cycle.id.desc()).all()
        cycle_id = request.args.get("cycle_id", type=int)
        cycle = (
            db.session.get(Cycle, cycle_id) if cycle_id else Cycle.get_active()
        ) or (cycles[0] if cycles else None)
        return self.render(
            "admin/equipment_conflicts.html",
            cycles=cycles,
            cycle=cycle,
            conflicts=reports.equipment_conflicts(cycle) if cycle else [],
        )


def init_admin(app):
    admin = Admin(
        app,
        name="Bell Tracker",
        theme=Bootstrap4Theme(),
        index_view=SecureAdminIndexView(),
    )
    admin.add_view(UserAdminView(User, db.session))
    admin.add_view(CycleAdminView(Cycle, db.session))
    admin.add_view(ProgramAdminView(Program, db.session))
    admin.add_view(PieceAdminView(Piece, db.session))
    admin.add_view(InstrumentTypeAdminView(InstrumentType, db.session))
    admin.add_view(CaseAdminView(Case, db.session))
    admin.add_view(EntryAdminView(Entry, db.session))
    admin.add_view(
        RosterImportView(name="Import positions", endpoint="roster_import")
    )
    admin.add_view(
        ProgressReportView(name="Progress report", endpoint="progress_report")
    )
    admin.add_view(
        EquipmentConflictsView(
            name="Equipment conflicts", endpoint="equipment_conflicts"
        )
    )
    return admin
