"""instrument_type form_label

What the ringer's equipment form calls a type, when that should differ
from its name. Singing Bell Sticks gets the singular, since a ringer
ticks for one.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'instrument_types',
        sa.Column('form_label', sa.String(length=100), nullable=True),
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE instrument_types SET form_label = 'Singing Bell Stick' "
            "WHERE name = 'Singing Bell Sticks'"
        )
    )


def downgrade():
    op.drop_column('instrument_types', 'form_label')
