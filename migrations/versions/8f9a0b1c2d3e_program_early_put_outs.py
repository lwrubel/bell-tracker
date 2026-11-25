"""program_early_put_outs

Lets an admin have an instrument type's items for the next set put out
before a set, so everything either set uses is out from the start.

Revision ID: 8f9a0b1c2d3e
Revises: 7e8f9a0b1c2d
Create Date: 2026-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f9a0b1c2d3e'
down_revision = '7e8f9a0b1c2d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'program_early_put_outs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('instrument_type_id', sa.Integer(), nullable=False),
        sa.Column('before_set', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id']),
        sa.ForeignKeyConstraint(['instrument_type_id'], ['instrument_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'instrument_type_id', 'before_set'),
    )


def downgrade():
    op.drop_table('program_early_put_outs')
