from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import DataRequired, Email, Optional

from app import pitch


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")


class MultiCheckboxField(SelectMultipleField):
    """A SelectMultipleField that renders as checkboxes instead of a
    <select multiple> list, so pitches can be picked without a keyboard
    modifier click."""

    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def instrument_field_name(instrument_type_id):
    return f"instrument_{instrument_type_id}"


def build_equipment_form(piece, formdata=None, **kwargs):
    """Build a form with one pitch-picker field per instrument type enabled
    on `piece`, plus a misc_notes field.

    The field set depends on which instrument types the piece has enabled,
    so the form class is constructed per request rather than being static.
    """
    attrs = {}
    for instrument_type in piece.instrument_types:
        # Value/label stay the sharp-spelled pitch (what's stored); the
        # template attaches a data-flat attribute to each checkbox (via the
        # flat_name Jinja global) so it can offer a flats display toggle
        # without touching what's actually submitted/stored.
        choices = [
            (p, p)
            for p in pitch.pitches_in_range(
                instrument_type.note_range_low, instrument_type.note_range_high
            )
        ]
        attrs[instrument_field_name(instrument_type.id)] = MultiCheckboxField(
            instrument_type.name, choices=choices, validators=[Optional()]
        )
    attrs["misc_notes"] = TextAreaField("Miscellaneous", validators=[Optional()])
    attrs["submit"] = SubmitField("Save")

    form_class = type("EquipmentForm", (FlaskForm,), attrs)
    return form_class(formdata=formdata, **kwargs)
