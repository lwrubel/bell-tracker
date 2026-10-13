"""enable main bells on every piece

Main Bells is back on the equipment form, as an optional sign-up. Marking
it enabled_by_default attaches it to new pieces (see the before_flush hook
in app/models.py); this backfills the pieces that already exist.
Downgrading only clears the flag; which pieces had Main Bells before isn't
kept.

Revision ID: 1e2f3a4b5c6d
Revises: 0d1e2f3a4b5c
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e2f3a4b5c6d'
down_revision = '0d1e2f3a4b5c'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "UPDATE instrument_types SET enabled_by_default = true "
            "WHERE name = 'Main Bells'"
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO piece_instrument_types (piece_id, instrument_type_id)
            SELECT p.id, it.id
            FROM pieces p
            CROSS JOIN instrument_types it
            WHERE it.name = 'Main Bells'
              AND NOT EXISTS (
                  SELECT 1 FROM piece_instrument_types x
                  WHERE x.piece_id = p.id AND x.instrument_type_id = it.id
              )
            """
        )
    )


def downgrade():
    op.get_bind().execute(
        sa.text(
            "UPDATE instrument_types SET enabled_by_default = false "
            "WHERE name = 'Main Bells'"
        )
    )
