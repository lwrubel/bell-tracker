from flask import redirect, request, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme
from flask_login import current_user
from wtforms import PasswordField, SelectField

from app import db, pitch
from app.models import Case, Concert, Entry, InstrumentType, Piece, User
from app.positions import POSITION_CODES

PITCH_CHOICES = [(p, p) for p in pitch.all_pitches()]
POSITION_CHOICES = [(c, c) for c in POSITION_CODES]


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
        elif is_created:
            raise Exception("Password is required when creating a user.")


class ConcertAdminView(SecureModelView):
    column_list = ("name", "date")
    # "id" must stay in form_columns even though it's not user-editable:
    # Flask-Admin's inline-form machinery reads it to tell new rows from
    # existing ones when saving. Omitting it raises
    # AttributeError: 'PieceForm' object has no attribute 'id'.
    inline_models = [(Piece, {"form_columns": ["id", "title", "program_order"]})]


class PieceAdminView(SecureModelView):
    column_list = ("concert", "title", "program_order", "instrument_types")
    form_columns = ("concert", "title", "program_order", "instrument_types")


class InstrumentTypeAdminView(SecureModelView):
    column_list = ("name", "note_range_low", "note_range_high")
    form_columns = ("name", "note_range_low", "note_range_high")
    form_overrides = {"note_range_low": SelectField, "note_range_high": SelectField}
    form_args = {
        "note_range_low": {"choices": PITCH_CHOICES},
        "note_range_high": {"choices": PITCH_CHOICES},
    }


class CaseAdminView(SecureModelView):
    column_list = ("case_number", "instrument_type", "note_range_low", "note_range_high")
    form_columns = ("case_number", "instrument_type", "note_range_low", "note_range_high")
    form_overrides = {"note_range_low": SelectField, "note_range_high": SelectField}
    form_args = {
        "note_range_low": {"choices": PITCH_CHOICES},
        "note_range_high": {"choices": PITCH_CHOICES},
    }

    def on_model_change(self, form, model, is_created):
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
    return ", ".join(
        f"{sel.instrument_type.name}: {sel.notes or ''}"
        for sel in model.instrument_selections
    )


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
