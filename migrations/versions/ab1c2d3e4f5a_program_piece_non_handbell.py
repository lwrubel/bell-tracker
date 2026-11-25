"""program_piece non_handbell

Marks a piece in a program as not rung on handbells, so Resets ignore it
when finding a set's first and last pieces. False for every existing
program piece, so Resets don't change.

Revision ID: ab1c2d3e4f5a
Revises: 9a0b1c2d3e4f
Create Date: 2026-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab1c2d3e4f5a'
down_revision = '9a0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.add_column(
            sa.Column(
                'non_handbell',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )


def downgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.drop_column('non_handbell')
