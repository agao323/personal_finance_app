"""Delete advisor rows past their retention: `make advisor-purge`.

The same purge runs at the start of every advisor request (`advisor/store.py`); this is for
running it without one — after a quiet month, say, or before a backup. It prints counts of
rows deleted and nothing else.
"""

from __future__ import annotations

import datetime as dt

from app.advisor.store import Store, fresh_transaction


def main() -> None:
    purged = Store(fresh_transaction).purge(dt.datetime.now(dt.UTC))
    print(
        f"advisor purge: {purged.conversations} conversations, "
        f"{purged.tool_calls} tool calls, {purged.usage} usage rows"
    )


if __name__ == "__main__":
    main()
