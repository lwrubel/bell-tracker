"""seed the Mallets instrument type and enable it on existing pieces

New pieces pick up color-mode instrument types automatically (see the
before_flush hook in app/models.py); this backfills the pieces that
already existed, and seeds a "Mallets" type if there isn't one yet so
there is something to enable.

Revision ID: c7e8a9b0c1d2
Revises: b1c2d3e4f5a6
Create Date: 2026-09-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e8a9b0c1d2'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    already_there = bind.execute(
        sa.text(
            "SELECT 1 FROM instrument_types "
            "WHERE selection_mode = 'color' OR name = 'Mallets' LIMIT 1"
        )
    ).first()
    if not already_there:
        bind.execute(
            sa.text(
                "INSERT INTO instrument_types (name, selection_mode) "
                "VALUES ('Mallets', 'color')"
            )
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO piece_instrument_types (piece_id, instrument_type_id)
            SELECT p.id, it.id
            FROM pieces p
            CROSS JOIN instrument_types it
            WHERE it.selection_mode = 'color'
              AND NOT EXISTS (
                  SELECT 1 FROM piece_instrument_types x
                  WHERE x.piece_id = p.id AND x.instrument_type_id = it.id
              )
            """
        )
    )


def downgrade():
    bind = op.get_bind()

    # Detach color-mode types from every piece...
    bind.execute(
        sa.text(
            "DELETE FROM piece_instrument_types WHERE instrument_type_id IN "
            "(SELECT id FROM instrument_types WHERE selection_mode = 'color')"
        )
    )
    # ...and drop the types themselves unless a ringer has signed up on one.
    # This also keeps the previous revision downgradable: it restores NOT NULL
    # on the note range columns, which color-mode rows leave null.
    bind.execute(
        sa.text(
            "DELETE FROM instrument_types WHERE selection_mode = 'color' "
            "AND id NOT IN (SELECT instrument_type_id FROM entry_instruments)"
        )
    )
