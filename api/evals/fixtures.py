"""`make eval-fixtures`: build the eval world, compute every fact, write `expected.json`.

Runs in `pfa_eval` (see `evals/database.py`), created and migrated if need be, inside one
transaction that is **rolled back**: the database is borrowed, not changed.
It still refuses a database whose `data_marker` says it is real — `overlay.build` checks
before it writes anything, rollback or not.
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from evals import EVAL_SEED, EVAL_TODAY, EXPECTED_PATH, database, overlay
from evals.facts import compute_all


def expected(session: Session) -> dict[str, object]:
    overlay.build(session)
    return {
        "today": EVAL_TODAY.isoformat(),
        "seed": EVAL_SEED,
        "facts": compute_all(session, EVAL_TODAY),
    }


def main() -> None:
    url = database.url()
    database.ensure(url)
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                data = expected(session)
        finally:
            transaction.rollback()
    EXPECTED_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED_PATH.name}: {len(data['facts'])} facts")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
