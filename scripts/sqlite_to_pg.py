"""One-off: copy the local SQLite database into Postgres.

Production starts empty, so this only ever runs against a local Postgres -
it's here to carry existing concerts, ringers and sign-ups across the
switch. Run it once against an already-migrated target:

    docker compose up -d db
    docker compose run --rm web flask --app wsgi db upgrade
    uv run python scripts/sqlite_to_pg.py instance/app.db

Both sides are read and written through SQLAlchemy rather than raw DBAPI
cursors, so each dialect handles its own marshalling: SQLite's 0/1 integers
come back as real bools, and its stringified dates as date/datetime objects,
before Postgres ever sees them.

The ORM is deliberately not used. The before_flush hook in app/models.py
attaches every enabled_by_default instrument type to any newly inserted
Piece, which would invent piece_instrument_types rows that aren't in the
source data.
"""

import argparse
import os
import sys

from sqlalchemy import create_engine, func, insert, select, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db, normalize_database_url  # noqa: E402


def copy_table(source, target, table):
    rows = [dict(row) for row in source.execute(select(table)).mappings()]
    if rows:
        target.execute(insert(table), rows)
    return len(rows)


def reset_sequence(target, table):
    """Realign the SERIAL sequence with the ids we inserted explicitly.

    Without this the next row created through the admin reuses id 1 and
    trips the primary key.
    """
    pk = list(table.primary_key.columns)
    if len(pk) != 1 or not pk[0].autoincrement:
        return  # association tables have a composite key and no sequence
    column = pk[0]
    target.execute(
        text(
            "SELECT setval("
            "  pg_get_serial_sequence(:table, :column),"
            "  GREATEST(COALESCE(MAX({col}), 0), 1),"
            "  MAX({col}) IS NOT NULL"
            ") FROM {table}".format(col=column.name, table=table.name)
        ),
        {"table": table.name, "column": column.name},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", help="path to the SQLite file, e.g. instance/app.db")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://bell:bell@localhost:5432/bell_tracker"
        ),
        help="Postgres target (default: the local docker compose database)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.sqlite_path):
        sys.exit(f"No such SQLite file: {args.sqlite_path}")

    # create_app() populates db.metadata with every model's table.
    create_app()
    metadata = db.metadata

    source_engine = create_engine(f"sqlite:///{os.path.abspath(args.sqlite_path)}")
    target_engine = create_engine(normalize_database_url(args.database_url))

    with source_engine.connect() as source, target_engine.begin() as target:
        missing = [
            t.name
            for t in metadata.sorted_tables
            if not target.dialect.has_table(target, t.name)
        ]
        if missing:
            sys.exit(
                "Target is missing tables: "
                + ", ".join(missing)
                + "\nRun `flask --app wsgi db upgrade` against it first."
            )

        # Clear the target first - `db upgrade` seeds a Mallets row, which
        # would collide with the one coming from SQLite on the unique name.
        for table in reversed(metadata.sorted_tables):
            target.execute(table.delete())

        for table in metadata.sorted_tables:
            count = copy_table(source, target, table)
            print(f"{table.name}: {count}")

        for table in metadata.sorted_tables:
            reset_sequence(target, table)

    with target_engine.connect() as target:
        users = target.execute(select(func.count()).select_from(metadata.tables["users"]))
        print(f"\nDone. {users.scalar()} users in {target_engine.url.render_as_string()}.")


if __name__ == "__main__":
    main()
