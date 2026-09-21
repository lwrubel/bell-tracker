"""instrument_type display_order

Gives the equipment form a deliberate order instead of whatever the
piece_instrument_types join happened to return. The bells are ranked in
tens so an admin can slot a new one between two existing ones; everything
else keeps the default of 100 and sorts to the end, which is where mallets
and any newly added type belong.

Ranks are applied by name and only to rows that exist - a fresh database
has just the Mallets row seeded by c7e8a9b0c1d2, which correctly stays at
the default.

Revision ID: f5a6b7c8d9e0
Revises: e3f4a5b6c7d8
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5a6b7c8d9e0'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None

# Mirrors DEFAULT_DISPLAY_ORDER in app/models.py, spelled out because a
# migration has to keep running against the schema of its own era.
DEFAULT_DISPLAY_ORDER = 100

RANKS = (
    ('Bass Bells', 10),
    ('Chimes', 20),
    ('Duplicate Bells', 30),
    ('Silver Melody Bells', 40),
    ('Petit & Fritsen', 50),
)


def upgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.add_column(
            sa.Column(
                'display_order',
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_DISPLAY_ORDER),
            )
        )

    bind = op.get_bind()
    for name, rank in RANKS:
        bind.execute(
            sa.text(
                "UPDATE instrument_types SET display_order = :rank WHERE name = :name"
            ),
            {"rank": rank, "name": name},
        )


def downgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.drop_column('display_order')
