"""user must_change_password

Flags users whose password was set by an admin so they're made to choose
their own at next login. Existing users default to false - they aren't
forced to change a password they already chose.

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(
            sa.Column(
                'must_change_password',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('must_change_password')
