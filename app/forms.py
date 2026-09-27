from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    PasswordField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
)

from app import color, pitch


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")


MIN_PASSWORD_LENGTH = 8


def _new_password_fields():
    return (
        PasswordField(
            "New password",
            validators=[DataRequired(), Length(min=MIN_PASSWORD_LENGTH)],
        ),
        PasswordField(
            "Confirm new password",
            validators=[
                DataRequired(),
                EqualTo("new_password", message="Passwords must match."),
            ],
        ),
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password, confirm = _new_password_fields()
    submit = SubmitField("Change password")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    new_password, confirm = _new_password_fields()
    submit = SubmitField("Reset password")


class MultiCheckboxField(SelectMultipleField):
    """A SelectMultipleField that renders as checkboxes instead of a
    <select multiple> list, so pitches can be picked without a keyboard
    modifier click."""

    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def instrument_field_name(instrument_type_id):
    return f"instrument_{instrument_type_id}"


def color_field_name(instrument_type_id, color_index):
    return f"color_{instrument_type_id}_{color_index}"


def other_label_field_name(instrument_type_id):
    return f"other_{instrument_type_id}_label"


def other_count_field_name(instrument_type_id):
    return f"other_{instrument_type_id}_count"


def _add_pitch_field(attrs, instrument_type):
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


def _add_color_fields(attrs, instrument_type):
    for index, color_name in enumerate(color.MALLET_COLORS):
        attrs[color_field_name(instrument_type.id, index)] = IntegerField(
            color_name, default=0, validators=[Optional(), NumberRange(min=0)]
        )
    attrs[other_label_field_name(instrument_type.id)] = StringField(
        "Other", validators=[Optional()]
    )
    attrs[other_count_field_name(instrument_type.id)] = IntegerField(
        "Other count", default=0, validators=[Optional(), NumberRange(min=0)]
    )


def build_equipment_form(entry, formdata=None, **kwargs):
    """Build a form with one picker per instrument type this ringer sees on
    their piece, plus a misc_notes field.

    Pitch-mode types get a pitch checkbox field; color-mode types get one
    integer count field per mallet color plus an "Other" label + count.
    The field set depends on the entry's visible instrument types, so the
    form class is constructed per request rather than being static.
    """
    attrs = {}
    for instrument_type in entry.visible_instrument_types():
        if instrument_type.selection_mode == "color":
            _add_color_fields(attrs, instrument_type)
        else:
            _add_pitch_field(attrs, instrument_type)
    attrs["misc_notes"] = TextAreaField(
        "Miscellaneous",
        validators=[Optional()],
        description=(
            "Other equipment such as singing bell stick, bell tree, "
            "or percussion instruments."
        ),
    )
    attrs["submit"] = SubmitField("Save")

    form_class = type("EquipmentForm", (FlaskForm,), attrs)
    return form_class(formdata=formdata, **kwargs)
