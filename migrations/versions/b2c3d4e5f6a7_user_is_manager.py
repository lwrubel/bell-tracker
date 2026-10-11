"""user is_manager

Managers see every program's reports without having the admin panel.
Existing users default to false.

Revision ID: b2c3d4e5f6a7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_manager',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_manager')
