"""Write the whole database to a JSON file on this machine.

**Layer two of the backup story, and it does not leave the machine.** See
[ADR 0008](../../docs/adr/0008-local-backups.md): the previous design shipped encrypted
dumps to Cloudflare R2 from GitHub Actions, which put the encryption key in the same
secret store as the R2 credentials and the database URL — concentrating precisely what it
claimed to separate. The data that is genuinely irreplaceable turned out to be one table,
`balance_snapshots`, and a file on a FileVault-encrypted disk protects it adequately.

**No encryption here, deliberately.** A second key to lose is the failure the old design
was rejected for, and this file never leaves a disk that is already encrypted.

Reads the database directly rather than calling `GET /export`, so it works from a terminal
without a Cloudflare Access session. The rows are the same rows.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select

from app.db import Base
from app.routers.export import EXPORTED

#: Where backups land. Gitignored, and the machine's own backup carries it from here.
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "backups"


def _driver(url: str) -> str:
    """Point a bare `postgresql://` URL at psycopg 3.

    Neon hands you `postgresql://...` and SQLAlchemy reads that as psycopg2, which is not
    installed. Pasting the string from the Neon console should just work.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _jsonable(value: Any) -> Any:
    """Dates as ISO strings, Decimals as strings.

    The same rule `routers/export.py` applies, and for the same reason: this is the file
    someone rebuilds from, and a float would quietly round the balances it exists to
    preserve.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def dump(database_url: str) -> dict[str, Any]:
    """Every exported table, as plain JSON-ready data."""
    engine = create_engine(_driver(database_url))
    tables = Base.metadata.tables
    with engine.connect() as connection:
        rows = {
            name: [
                {column: _jsonable(value) for column, value in row._mapping.items()}
                for row in connection.execute(select(tables[name])).all()
            ]
            for name in EXPORTED
        }
    engine.dispose()
    return {
        "meta": {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "counts": {name: len(table) for name, table in rows.items()},
        },
        **rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("BACKUP_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="Defaults to BACKUP_DATABASE_URL, then DATABASE_URL.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite today's file. Without it, a second run the same day refuses.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        # Naming what is missing rather than failing obscurely, and never printing the
        # value of anything.
        print(
            "No database URL. Set BACKUP_DATABASE_URL in .env, or pass --database-url.",
            file=sys.stderr,
        )
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"pfa-{dt.date.today().isoformat()}.json"
    if path.exists() and not args.force:
        # Refusing rather than overwriting: a second run after a bad restore should not
        # replace the good copy from this morning.
        print(f"{path} already exists. Pass --force to replace it.", file=sys.stderr)
        return 1

    data = dump(args.database_url)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    counts = data["meta"]["counts"]
    size_kb = path.stat().st_size / 1024
    print(f"wrote {path} ({size_kb:.0f} KB)")
    # Row counts per table, because "it wrote a file" is not evidence it wrote the data.
    for name in EXPORTED:
        print(f"  {counts[name]:>7}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
