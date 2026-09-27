from flask import redirect, request, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme
from flask_login import current_user
from wtforms import PasswordField, SelectField

from app import color, db, pitch
from app.models import Case, Concert, Entry, InstrumentType, Piece, User
from app.positions import POSITION_CODES, position_prefixes

PITCH_CHOICES = [(p, p) for p in pitch.all_pitches()]
# Range is optional for color-mode instrument types, so offer a blank choice.
OPTIONAL_PITCH_CHOICES = [("", "— none —")] + PITCH_CHOICES
POSITION_CHOICES = [(c, c) for c in POSITION_CODES]
SELECTION_MODE_CHOICES = [("pitch", "pitch"), ("color", "color")]
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
    column_list = ("email", "name", "is_admin")
    form_columns = ("email", "name", "is_admin", "password")
    form_extra_fields = {"password": PasswordField("Password")}

    def on_model_change(self, form, model, is_created):
        model.email = model.email.strip().lower()
        if form.password.data:
            model.set_password(form.password.data)
            # A password an admin chose is a temporary one - unless the admin
            # is setting their own.
            if model.id is None or model.id != current_user.id:
                model.must_change_password = True
        elif is_created:
            raise Exception("Password is required when creating a user.")


class ConcertAdminView(SecureModelView):
    column_list = ("name",)
    # "id" must stay in form_columns even though it's not user-editable:
    # Flask-Admin's inline-form machinery reads it to tell new rows from
    # existing ones when saving. Omitting it raises
    # AttributeError: 'PieceForm' object has no attribute 'id'.
    inline_models = [(Piece, {"form_columns": ["id", "title", "program_order"]})]


class PieceAdminView(SecureModelView):
    column_list = ("concert", "title", "program_order", "instrument_types")
    form_columns = ("concert", "title", "program_order", "instrument_types")


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
    }

    def on_model_change(self, form, model, is_created):
        # "" from the blank choice means "no restriction", not a prefix.
        if not model.position_prefix:
            model.position_prefix = None
        if model.selection_mode == "color":
            # Color-mode types (mallets) pick from app/color.py, not pitches.
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
    column_list = ("case_number", "instrument_type", "note_range_low", "note_range_high")
    form_columns = ("case_number", "instrument_type", "note_range_low", "note_range_high")
    form_overrides = {"note_range_low": SelectField, "note_range_high": SelectField}
    form_args = {
        "note_range_low": {"choices": PITCH_CHOICES},
        "note_range_high": {"choices": PITCH_CHOICES},
    }

    def on_model_change(self, form, model, is_created):
        if model.instrument_type.selection_mode == "color":
            raise Exception("Cases only apply to pitch-based instrument types.")
        type_low = model.instrument_type.note_range_low
        type_high = model.instrument_type.note_range_high
        if not pitch.in_range(model.note_range_low, type_low, type_high) or not pitch.in_range(
            model.note_range_high, type_low, type_high
        ):
            raise Exception(
                f"Case range must fall within {model.instrument_type.name}'s "
                f"range ({type_low}-{type_high})."
            )


def _format_instrument_selections(view, context, model, name):
    parts = []
    for sel in model.instrument_selections:
        instrument_type = sel.instrument_type
        if instrument_type.selection_mode == "color":
            body = ", ".join(
                f"{label} ×{count}" for label, count in sel.color_counts()
            )
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
    column_formatters = {"instrument_selections": _format_instrument_selections}
    can_view_details = True
    form_columns = ("user", "piece", "position")
    form_overrides = {"position": SelectField}
    form_args = {"position": {"choices": POSITION_CHOICES}}


def init_admin(app):
    admin = Admin(
        app,
        name="bell-tracker",
        theme=Bootstrap4Theme(),
        index_view=SecureAdminIndexView(),
    )
    admin.add_view(UserAdminView(User, db.session))
    admin.add_view(ConcertAdminView(Concert, db.session))
    admin.add_view(PieceAdminView(Piece, db.session))
    admin.add_view(InstrumentTypeAdminView(InstrumentType, db.session))
    admin.add_view(CaseAdminView(Case, db.session))
    admin.add_view(EntryAdminView(Entry, db.session))
    return admin
