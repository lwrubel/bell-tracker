from flask import flash, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme
from flask_login import current_user
from wtforms import PasswordField, SelectField

from app import color, db, pitch, roster_import
from app.models import (
    Case,
    Cycle,
    Entry,
    InstrumentOption,
    InstrumentType,
    Piece,
    Program,
    ProgramPiece,
    User,
)
from app.positions import POSITION_CODES, position_label, position_prefixes

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
    column_list = ("cycle", "name", "datetime")
    form_columns = ("cycle", "name", "datetime")
    column_labels = {"datetime": "Date and time"}
    # The pieces this program plays, numbered in program order. See
    # CycleAdminView for why "id" is listed.
    # "Position" means a ringer's spot in a piece everywhere else, so the
    # piece's place in the program is labelled "Order" here.
    inline_models = [
        (
            ProgramPiece,
            {
                "form_columns": ["id", "piece", "position"],
                "form_args": {"position": {"label": "Order"}},
            },
        )
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
    )
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

    Equipment fields (misc_notes, instrument selections) are the ringer's to
    fill in from the front end; shown here read-only for troubleshooting.
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
    form_columns = ("user", "piece", "position")
    form_overrides = {"position": SelectField}
    form_args = {"position": {"choices": POSITION_CHOICES}}


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


def init_admin(app):
    admin = Admin(
        app,
        name="bell-tracker",
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
    return admin
