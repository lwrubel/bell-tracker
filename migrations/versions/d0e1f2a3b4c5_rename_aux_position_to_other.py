"""rename Aux position to Other

The roster spreadsheets call this position "Other", so the code follows.
Rewrites existing assignments and any instrument type limited to it.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def _rename(old, new):
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE entries SET position = :new WHERE position = :old"),
        {"old": old, "new": new},
    )
    bind.execute(
        sa.text(
            "UPDATE instrument_types SET position_prefix = :new "
            "WHERE position_prefix = :old"
        ),
        {"old": old, "new": new},
    )


def upgrade():
    _rename("Aux", "Other")


def downgrade():
    _rename("Other", "Aux")
