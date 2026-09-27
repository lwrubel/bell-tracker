"""drop concert date

Concerts are identified by name alone; the date was never used for
anything but display and ordering, which now goes by creation order.

Downgrade restores the column as NOT NULL, filling existing rows with
the day of the downgrade since the original dates are gone.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('concerts') as batch_op:
        batch_op.drop_column('date')


def downgrade():
    with op.batch_alter_table('concerts') as batch_op:
        batch_op.add_column(
            sa.Column(
                'date',
                sa.Date(),
                nullable=False,
                server_default=sa.text('CURRENT_DATE'),
            )
        )
    with op.batch_alter_table('concerts') as batch_op:
        batch_op.alter_column('date', server_default=None)
