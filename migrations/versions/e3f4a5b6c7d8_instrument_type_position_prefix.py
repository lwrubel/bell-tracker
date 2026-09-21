"""instrument_type position_prefix + enabled_by_default

Adds the two flags that decide *where* a type is enabled and *who* sees it,
then backfills them:

- enabled_by_default replaces the old "auto-enable color-mode types on new
  pieces" rule, so it is set on the existing color-mode types (mallets) to
  keep that behavior identical.
- Bass Bells becomes LB-only and enabled everywhere.

downgrade() drops both columns but deliberately leaves piece_instrument_types
alone: it can't tell the links it added from ones that were already there,
so detaching would lose real data.

Revision ID: e3f4a5b6c7d8
Revises: c7e8a9b0c1d2
Create Date: 2026-09-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = 'c7e8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.add_column(
            sa.Column('position_prefix', sa.String(length=10), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'enabled_by_default',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )

    bind = op.get_bind()

    # Preserve today's behavior: color-mode types were auto-enabled on new
    # pieces by virtue of their mode; now it's this flag that does it.
    bind.execute(
        sa.text(
            "UPDATE instrument_types SET enabled_by_default = true "
            "WHERE selection_mode = 'color'"
        )
    )
    # Bass bells belong to the LB positions, on every piece.
    bind.execute(
        sa.text(
            "UPDATE instrument_types "
            "SET position_prefix = 'LB', enabled_by_default = true "
            "WHERE name = 'Bass Bells'"
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO piece_instrument_types (piece_id, instrument_type_id)
            SELECT p.id, it.id
            FROM pieces p
            CROSS JOIN instrument_types it
            WHERE it.enabled_by_default = true
              AND NOT EXISTS (
                  SELECT 1 FROM piece_instrument_types x
                  WHERE x.piece_id = p.id AND x.instrument_type_id = it.id
              )
            """
        )
    )


def downgrade():
    with op.batch_alter_table('instrument_types') as batch_op:
        batch_op.drop_column('enabled_by_default')
        batch_op.drop_column('position_prefix')
