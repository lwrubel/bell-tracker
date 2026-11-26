"""program pull_list_notes

Free-text notes an admin adds to a program's Equipment pull list, for
set-up instructions that don't come from ringers' entries.

Revision ID: bc2d3e4f5a6b
Revises: ab1c2d3e4f5a
Create Date: 2026-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc2d3e4f5a6b'
down_revision = 'ab1c2d3e4f5a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('programs') as batch_op:
        batch_op.add_column(sa.Column('pull_list_notes', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('programs') as batch_op:
        batch_op.drop_column('pull_list_notes')
