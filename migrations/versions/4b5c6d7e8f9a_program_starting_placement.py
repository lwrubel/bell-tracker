"""program starting_placement

Lets an admin turn on the Starting placement report for the programs that
need it. Off for every existing program.

Revision ID: 4b5c6d7e8f9a
Revises: 3a4b5c6d7e8f
Create Date: 2026-11-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b5c6d7e8f9a'
down_revision = '3a4b5c6d7e8f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('programs') as batch_op:
        batch_op.add_column(
            sa.Column(
                'starting_placement',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )


def downgrade():
    with op.batch_alter_table('programs') as batch_op:
        batch_op.drop_column('starting_placement')
