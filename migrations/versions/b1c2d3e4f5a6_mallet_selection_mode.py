"""instrument_type selection_mode + nullable note ranges

Revision ID: b1c2d3e4f5a6
Revises: 4a03644f7c50
Create Date: 2026-09-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = '4a03644f7c50'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.add_column(
            sa.Column(
                'selection_mode',
                sa.String(length=10),
                nullable=False,
                server_default='pitch',
            )
        )
        batch_op.alter_column(
            'note_range_low', existing_type=sa.String(length=10), nullable=True
        )
        batch_op.alter_column(
            'note_range_high', existing_type=sa.String(length=10), nullable=True
        )


def downgrade():
    # Color-mode rows leave the note range null, and a later revision keeps
    # any that a ringer has signed up on - so fill those in with the full
    # chromatic range before putting NOT NULL back, or the batch rebuild
    # fails with an IntegrityError.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE instrument_types SET note_range_low = 'C1' "
            "WHERE note_range_low IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE instrument_types SET note_range_high = 'C9' "
            "WHERE note_range_high IS NULL"
        )
    )

    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.alter_column(
            'note_range_high', existing_type=sa.String(length=10), nullable=False
        )
        batch_op.alter_column(
            'note_range_low', existing_type=sa.String(length=10), nullable=False
        )
        batch_op.drop_column('selection_mode')
