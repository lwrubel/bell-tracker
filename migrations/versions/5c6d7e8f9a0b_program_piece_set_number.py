"""program_piece set_number

Lets an admin split a program into sets, with a Reset between them. Null
for every existing program piece, so no program has sets yet.

Revision ID: 5c6d7e8f9a0b
Revises: 4b5c6d7e8f9a
Create Date: 2026-11-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c6d7e8f9a0b'
down_revision = '4b5c6d7e8f9a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.add_column(sa.Column('set_number', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('program_pieces') as batch_op:
        batch_op.drop_column('set_number')
