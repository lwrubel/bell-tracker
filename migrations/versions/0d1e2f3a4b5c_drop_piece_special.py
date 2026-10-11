"""drop piece special

The flag only drove the reports' include/exclude special pieces switch,
which is gone. Downgrading brings the column back with every piece set to
false; which pieces were special isn't kept.

Revision ID: 0d1e2f3a4b5c
Revises: f6a7b8c9d0e1
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0d1e2f3a4b5c'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pieces') as batch_op:
        batch_op.drop_column('special')


def downgrade():
    with op.batch_alter_table('pieces') as batch_op:
        batch_op.add_column(
            sa.Column(
                'special',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )
