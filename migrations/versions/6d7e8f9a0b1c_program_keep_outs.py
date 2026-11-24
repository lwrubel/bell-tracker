"""program_keep_outs

Lets an admin leave an instrument type on the table at the Reset after a
set, so it stays out for the next set instead of being taken off.

Revision ID: 6d7e8f9a0b1c
Revises: 5c6d7e8f9a0b
Create Date: 2026-11-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d7e8f9a0b1c'
down_revision = '5c6d7e8f9a0b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'program_keep_outs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('instrument_type_id', sa.Integer(), nullable=False),
        sa.Column('after_set', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id']),
        sa.ForeignKeyConstraint(['instrument_type_id'], ['instrument_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'instrument_type_id', 'after_set'),
    )


def downgrade():
    op.drop_table('program_keep_outs')
