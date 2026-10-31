"""entry equipment_saved_at

Records when a ringer saves the equipment form, so saving with nothing
selected still marks the piece as entered. Existing entries stay null;
those with equipment are still counted by what they hold.

Revision ID: 2f3a4b5c6d7e
Revises: 1e2f3a4b5c6d
Create Date: 2026-10-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f3a4b5c6d7e'
down_revision = '1e2f3a4b5c6d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entries') as batch_op:
        batch_op.add_column(sa.Column('equipment_saved_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('entries') as batch_op:
        batch_op.drop_column('equipment_saved_at')
