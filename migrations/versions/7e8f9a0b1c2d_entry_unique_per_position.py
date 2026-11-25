"""entry unique per position

Lets a ringer be assigned more than one position on a piece: an entry is
now unique per (user, piece, position) rather than (user, piece).

Revision ID: 7e8f9a0b1c2d
Revises: 6d7e8f9a0b1c
Create Date: 2026-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e8f9a0b1c2d'
down_revision = '6d7e8f9a0b1c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entries') as batch_op:
        batch_op.drop_constraint('entries_user_id_piece_id_key', type_='unique')
        batch_op.create_unique_constraint(
            'entries_user_id_piece_id_position_key',
            ['user_id', 'piece_id', 'position'],
        )


def downgrade():
    # Fails if any ringer has more than one position on a piece; remove
    # the extra entries first.
    with op.batch_alter_table('entries') as batch_op:
        batch_op.drop_constraint(
            'entries_user_id_piece_id_position_key', type_='unique'
        )
        batch_op.create_unique_constraint(
            'entries_user_id_piece_id_key', ['user_id', 'piece_id']
        )
