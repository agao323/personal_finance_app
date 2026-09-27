"""Load a local export back into a database.

**The acceptance criterion of ticket 017 is that this has actually been run**, not that
`export_local.py` produces a file. An export nobody has read back is a file you believe in.

Refuses a target that already holds rows unless `--force` is given, and never defaults to
production: the URL must be passed or come from `DATABASE_URL`, which in this repo is the
local Docker database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import Table, create_engine, delete, func, insert, select

from app.db import Base
from app.routers.export import EXPORTED


def _driver(url: str) -> str:
    """Point a bare `postgresql://` URL at psycopg 3.

    Neon hands you `postgresql://...` and SQLAlchemy reads that as psycopg2, which is not
    installed. Pasting the string from the Neon console should just work.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


#: Tables whose emptiness decides whether a target counts as fresh.
#:
#: **Not every table.** A database that has only just been migrated already holds seeded
#: categories, a user row, and the data marker, so checking everything would refuse every
#: legitimate restore and train you to pass `--force` by reflex — which is exactly when the
#: guard stops protecting the case it exists for. These four are the ones that mean somebody
#: has actually used this database.
SUBSTANTIVE = ("accounts", "balance_snapshots", "transactions", "card_perks")


def _occupied(connection: Any) -> list[str]:
    """Substantive tables with rows, so a restore cannot quietly land on top of real data."""
    tables = Base.metadata.tables
    return [
        name
        for name in SUBSTANTIVE
        if connection.execute(select(func.count()).select_from(tables[name])).scalar_one()
    ]


def _self_referencing_column(table: Table) -> str | None:
    """The column by which a table points at itself, if it has one.

    `categories` does, via `parent_id`. Table ordering cannot help there — the rows inside
    one insert have to be ordered too.
    """
    for column in table.columns:
        for key in column.foreign_keys:
            if key.column.table is table:
                return column.name
    return None


def _ordered(table: Table, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows in an order Postgres will accept, for a table that references itself.

    Parents before children. **One level deep**, which is what `categories` is; a deeper
    tree would need a topological sort of the rows themselves, and inventing one for a
    shape this schema does not have would be guessing at a future.
    """
    column = _self_referencing_column(table)
    if column is None:
        return rows
    return [row for row in rows if row.get(column) is None] + [
        row for row in rows if row.get(column) is not None
    ]


def insert_order() -> list[Table]:
    """The exported tables, parents first.

    **Derived from the schema, not hand-maintained.** `EXPORTED` is the response contract's
    field order and says nothing about foreign keys; using it here put `ownership_stakes`
    before `users`, and the first restore drill failed on that foreign key. `sorted_tables`
    comes from the same metadata Alembic autogenerates against, so it cannot fall out of
    step with the schema the way a second list would.
    """
    exported = set(EXPORTED)
    return [table for table in Base.metadata.sorted_tables if table.name in exported]


def restore(database_url: str, payload: dict[str, Any], *, force: bool) -> dict[str, int]:
    engine = create_engine(_driver(database_url))
    order = insert_order()
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        occupied = _occupied(connection)
        if occupied and not force:
            raise SystemExit(
                f"Target is not empty ({', '.join(occupied)}). Pass --force to replace."
            )
        # Children first on the way out, parents first on the way in.
        for table in reversed(order):
            connection.execute(delete(table))
        for table in order:
            rows = payload.get(table.name, [])
            if rows:
                connection.execute(insert(table), _ordered(table, rows))
            counts[table.name] = len(rows)
    engine.dispose()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="An export written by export_local.py")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Defaults to DATABASE_URL, which is the local database in this repo.",
    )
    parser.add_argument("--force", action="store_true", help="Replace rows already there.")
    args = parser.parse_args(argv)

    if not args.database_url:
        print("No database URL. Set DATABASE_URL or pass --database-url.", file=sys.stderr)
        return 2

    payload = json.loads(args.file.read_text())
    counts = restore(args.database_url, payload, force=args.force)

    print(f"restored {args.file}")
    for name in EXPORTED:
        print(f"  {counts[name]:>7}  {name}")
    # The comparison is the point of the drill, so print what to compare against.
    print("\nCompare these against the counts in the file's meta block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
