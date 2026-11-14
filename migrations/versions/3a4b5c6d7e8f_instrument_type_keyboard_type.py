"""instrument_type keyboard_type

Marks instrument types whose pitches are set up together as one instrument
(bell trees), so the Equipment Tables list them in their own section
instead of sorting each pitch into a position's range. Replaces the
hard-coded list of bell tree names in app/reports.py; the two types on it
are backfilled so nothing changes for them.

Revision ID: 3a4b5c6d7e8f
Revises: 2f3a4b5c6d7e
Create Date: 2026-11-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a4b5c6d7e8f'
down_revision = '2f3a4b5c6d7e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.add_column(
            sa.Column(
                'keyboard_type',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )

    op.get_bind().execute(
        sa.text(
            "UPDATE instrument_types SET keyboard_type = true "
            "WHERE name IN ('Bell Tree', 'SMB Bell Tree')"
        )
    )


def downgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.drop_column('keyboard_type')
