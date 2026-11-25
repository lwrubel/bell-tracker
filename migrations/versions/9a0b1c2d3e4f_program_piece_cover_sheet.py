"""program_piece cover_sheet

Lets a piece be in a program without getting a cover sheet. True for every
existing program piece, so the cover sheets don't change.

Revision ID: 9a0b1c2d3e4f
Revises: 8f9a0b1c2d3e
Create Date: 2026-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a0b1c2d3e4f'
down_revision = '8f9a0b1c2d3e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.add_column(
            sa.Column(
                'cover_sheet',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('true'),
            )
        )


def downgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.drop_column('cover_sheet')
