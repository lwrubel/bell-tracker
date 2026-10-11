"""cycles and programs

Concerts become programs, grouped into cycles. A piece now belongs to a
cycle, and each program picks some of its cycle's pieces in its own
order (program_pieces). Existing concerts all go into one active cycle,
keeping their pieces and order.

Downgrade puts each piece back under the first program that plays it.
Pieces in no program can't be placed, so downgrade refuses rather than
lose them.

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f7
Create Date: 2026-10-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    op.create_table(
        'cycles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column(
            'active', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'uq_cycles_one_active',
        'cycles',
        ['active'],
        unique=True,
        postgresql_where=sa.text('active'),
        sqlite_where=sa.text('active'),
    )

    cycle_id = None
    if conn.execute(sa.text('SELECT 1 FROM concerts LIMIT 1')).first():
        conn.execute(
            sa.text("INSERT INTO cycles (name, active) VALUES ('Current cycle', true)")
        )
        cycle_id = conn.execute(sa.text('SELECT id FROM cycles')).scalar_one()

    op.rename_table('concerts', 'programs')
    with op.batch_alter_table('programs') as batch_op:
        batch_op.add_column(sa.Column('cycle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('datetime', sa.DateTime(), nullable=True))
    if cycle_id is not None:
        conn.execute(
            sa.text('UPDATE programs SET cycle_id = :c'), {'c': cycle_id}
        )
    with op.batch_alter_table('programs') as batch_op:
        batch_op.alter_column('cycle_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            'programs_cycle_id_fkey', 'cycles', ['cycle_id'], ['id']
        )

    op.create_table(
        'program_pieces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('piece_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['piece_id'], ['pieces.id']),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'piece_id'),
    )
    conn.execute(
        sa.text(
            'INSERT INTO program_pieces (program_id, piece_id, position) '
            'SELECT concert_id, id, program_order FROM pieces'
        )
    )

    with op.batch_alter_table('pieces') as batch_op:
        batch_op.add_column(sa.Column('cycle_id', sa.Integer(), nullable=True))
    if cycle_id is not None:
        conn.execute(sa.text('UPDATE pieces SET cycle_id = :c'), {'c': cycle_id})
    with op.batch_alter_table('pieces') as batch_op:
        batch_op.alter_column('cycle_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            'pieces_cycle_id_fkey', 'cycles', ['cycle_id'], ['id']
        )
        batch_op.drop_constraint(
            'pieces_concert_id_program_order_key', type_='unique'
        )
        batch_op.drop_constraint('pieces_concert_id_fkey', type_='foreignkey')
        batch_op.drop_column('concert_id')
        batch_op.drop_column('program_order')


def downgrade():
    conn = op.get_bind()

    unplaced = conn.execute(
        sa.text(
            'SELECT count(*) FROM pieces WHERE id NOT IN '
            '(SELECT piece_id FROM program_pieces)'
        )
    ).scalar_one()
    if unplaced:
        raise RuntimeError(
            f'{unplaced} piece(s) are in no program; add them to one or '
            'delete them before downgrading.'
        )

    with op.batch_alter_table('pieces') as batch_op:
        batch_op.add_column(sa.Column('concert_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('program_order', sa.Integer(), nullable=True))
    # Each piece goes back to the lowest-numbered program that plays it.
    conn.execute(
        sa.text(
            'UPDATE pieces SET '
            'concert_id = (SELECT min(pp.program_id) FROM program_pieces pp '
            '              WHERE pp.piece_id = pieces.id), '
            'program_order = (SELECT pp.position FROM program_pieces pp '
            '                 WHERE pp.piece_id = pieces.id '
            '                 ORDER BY pp.program_id LIMIT 1)'
        )
    )
    op.drop_table('program_pieces')
    with op.batch_alter_table('pieces') as batch_op:
        batch_op.drop_constraint('pieces_cycle_id_fkey', type_='foreignkey')
        batch_op.drop_column('cycle_id')
        batch_op.alter_column('concert_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            'program_order', existing_type=sa.Integer(), nullable=False
        )

    with op.batch_alter_table('programs') as batch_op:
        batch_op.drop_constraint('programs_cycle_id_fkey', type_='foreignkey')
        batch_op.drop_column('cycle_id')
        batch_op.drop_column('datetime')
    op.rename_table('programs', 'concerts')

    with op.batch_alter_table('pieces') as batch_op:
        batch_op.create_foreign_key(
            'pieces_concert_id_fkey', 'concerts', ['concert_id'], ['id']
        )
        batch_op.create_unique_constraint(
            'pieces_concert_id_program_order_key', ['concert_id', 'program_order']
        )

    op.drop_index('uq_cycles_one_active', table_name='cycles')
    op.drop_table('cycles')
