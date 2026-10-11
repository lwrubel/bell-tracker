"""instrument_options, and seed the Percussion instrument type

An options-mode type lets ringers tick any of a list of options the admin
manages. Percussion starts with Triangle, Slap Stick and Jingle Bells. It
isn't enabled by default: the admin adds it to the pieces that use it.

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None

NAME = 'Percussion'
OPTIONS = ('Triangle', 'Slap Stick', 'Jingle Bells')
# Mirrors DEFAULT_DISPLAY_ORDER in app/models.py.
DISPLAY_ORDER = 100


def upgrade():
    op.create_table(
        'instrument_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instrument_type_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['instrument_type_id'], ['instrument_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_type_id', 'name'),
    )

    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT 1 FROM instrument_types WHERE name = :name"), {"name": NAME}
    ).first():
        # Someone already made one by hand; leave it for the admin to set up.
        return
    type_id = bind.execute(
        sa.text(
            "INSERT INTO instrument_types "
            "(name, selection_mode, enabled_by_default, display_order) "
            "VALUES (:name, 'options', false, :display_order) RETURNING id"
        ),
        {"name": NAME, "display_order": DISPLAY_ORDER},
    ).scalar_one()
    for option in OPTIONS:
        bind.execute(
            sa.text(
                "INSERT INTO instrument_options (instrument_type_id, name) "
                "VALUES (:type_id, :name)"
            ),
            {"type_id": type_id, "name": option},
        )


def downgrade():
    # Earlier code treats anything it doesn't know as pitches, so
    # options-mode types and every sign-up on them go.
    bind = op.get_bind()
    type_ids = "(SELECT id FROM instrument_types WHERE selection_mode = 'options')"
    bind.execute(
        sa.text(f"DELETE FROM entry_instruments WHERE instrument_type_id IN {type_ids}")
    )
    bind.execute(
        sa.text(
            f"DELETE FROM piece_instrument_types WHERE instrument_type_id IN {type_ids}"
        )
    )
    op.drop_table('instrument_options')
    bind.execute(sa.text("DELETE FROM instrument_types WHERE selection_mode = 'options'"))
