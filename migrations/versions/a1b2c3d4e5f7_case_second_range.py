"""case second range

Some cases hold two separate runs of bells, so a case gets an optional
second low/high pair. Existing cases keep a single range.

Revision ID: a1b2c3d4e5f7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cases') as batch_op:
        batch_op.add_column(
            sa.Column('second_range_low', sa.String(length=10), nullable=True)
        )
        batch_op.add_column(
            sa.Column('second_range_high', sa.String(length=10), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('cases') as batch_op:
        batch_op.drop_column('second_range_high')
        batch_op.drop_column('second_range_low')
