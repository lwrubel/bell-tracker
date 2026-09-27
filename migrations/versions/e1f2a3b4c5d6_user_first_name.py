"""user first_name

The name roster spreadsheets use for a ringer, matched by the position
importer. Existing users get the first word of their name.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('first_name', sa.String(length=80), nullable=True))
    op.execute("UPDATE users SET first_name = split_part(btrim(name), ' ', 1)")
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('first_name', nullable=False)


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('first_name')
