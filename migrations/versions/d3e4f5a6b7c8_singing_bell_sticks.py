"""seed the Singing Bell Sticks instrument type

A checkbox-mode type: each ringer ticks whether they need a stick on a
piece. It's enabled by default, so new pieces get it from the before_flush
hook in app/models.py; this attaches it to the pieces that already exist.

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None

NAME = 'Singing Bell Sticks'
# Mirrors DEFAULT_DISPLAY_ORDER in app/models.py, so it sorts with Mallets
# at the end of the equipment form.
DISPLAY_ORDER = 100


def upgrade():
    bind = op.get_bind()

    exists = bind.execute(
        sa.text("SELECT 1 FROM instrument_types WHERE name = :name"),
        {"name": NAME},
    ).first()
    if exists:
        bind.execute(
            sa.text(
                "UPDATE instrument_types SET selection_mode = 'checkbox', "
                "note_range_low = NULL, note_range_high = NULL, "
                "enabled_by_default = true WHERE name = :name"
            ),
            {"name": NAME},
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO instrument_types "
                "(name, selection_mode, enabled_by_default, display_order) "
                "VALUES (:name, 'checkbox', true, :display_order)"
            ),
            {"name": NAME, "display_order": DISPLAY_ORDER},
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO piece_instrument_types (piece_id, instrument_type_id)
            SELECT p.id, it.id
            FROM pieces p
            CROSS JOIN instrument_types it
            WHERE it.name = :name
              AND NOT EXISTS (
                  SELECT 1 FROM piece_instrument_types x
                  WHERE x.piece_id = p.id AND x.instrument_type_id = it.id
              )
            """
        ),
        {"name": NAME},
    )


def downgrade():
    # Earlier code treats anything that isn't color-mode as pitches, so the
    # type and every sign-up on it go, rather than lingering as a pitch type
    # with no range.
    bind = op.get_bind()
    params = {"name": NAME}
    type_ids = "(SELECT id FROM instrument_types WHERE name = :name)"
    bind.execute(
        sa.text(f"DELETE FROM entry_instruments WHERE instrument_type_id IN {type_ids}"),
        params,
    )
    bind.execute(
        sa.text(
            f"DELETE FROM piece_instrument_types WHERE instrument_type_id IN {type_ids}"
        ),
        params,
    )
    bind.execute(sa.text("DELETE FROM instrument_types WHERE name = :name"), params)
