"""Balance snapshots: the write path and the point-in-time lookup.

Current balance is **derived** as the latest snapshot, never stored on ``accounts``.
Duplicating it would create a second source of truth that can disagree with the
history, and the disagreement would be invisible until a chart looked wrong.

History that is not captured cannot be recovered later, so every balance write appends
a snapshot rather than overwriting a field.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot
from app.models.enums import DataSource

#: How long a balance may be carried forward before it is flagged.
#:
#: Carry-forward is required for a usable chart — nobody records every account every
#: day — but *unbounded* carry-forward is a correctness bug: an account someone stopped
#: updating would contribute its last known value to net worth for ever. Three months
#: is roughly a quarterly statement cycle, so a normally-maintained account never trips
#: it and a forgotten one does.
STALE_AFTER = dt.timedelta(days=90)


@dataclass(frozen=True)
class BalanceAt:
    """A balance resolved for a date, with the provenance needed to judge it."""

    balance: Decimal
    as_of: dt.date
    """The date of the snapshot the value came from, not the date asked for."""
    source: DataSource
    is_stale: bool
    """True when the snapshot is older than :data:`STALE_AFTER`.

    Returned rather than dropped: a stale number surfaced with a warning is useful,
    and silently omitting the account would make net worth quietly drop instead.
    """


def record_balance(
    session: Session,
    account_id: int,
    as_of: dt.date,
    balance: Decimal,
    source: DataSource = DataSource.MANUAL,
) -> BalanceSnapshot:
    """Upsert the snapshot for a date.

    Re-recording the same date replaces the value rather than failing or duplicating,
    so correcting a typo is one call and re-importing a file changes nothing. The
    unique constraint on (account_id, as_of) makes that atomic at the database rather
    than a read-then-write race.
    """
    statement = (
        insert(BalanceSnapshot)
        .values(account_id=account_id, as_of=as_of, balance=balance, source=source)
        .on_conflict_do_update(
            constraint="uq_snapshot_account_date",
            set_={"balance": balance, "source": source},
        )
        .returning(BalanceSnapshot)
    )
    snapshot = session.execute(statement).scalar_one()
    session.flush()
    return snapshot


def balance_in_force(session: Session, account_id: int, as_of: dt.date) -> BalanceAt | None:
    """The account's balance on ``as_of``, carried forward from the latest snapshot.

    Returns ``None`` when the account had no snapshot by that date, or when it was
    already closed. Excluding an account with no history is deliberate: treating it as
    zero would make a newly-added account appear to have dropped a fortune the day
    before it existed.
    """
    account = session.get(Account, account_id)
    if account is None:
        return None

    # A sold car or a paid-off loan must leave net worth on the day it closes.
    # Together with the staleness cap this is what stops carry-forward from keeping
    # dead accounts alive for ever.
    if account.closed_at is not None and account.closed_at <= as_of:
        return None

    snapshot = session.execute(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account_id, BalanceSnapshot.as_of <= as_of)
        .order_by(BalanceSnapshot.as_of.desc())
        .limit(1)
    ).scalar_one_or_none()

    if snapshot is None:
        return None

    return BalanceAt(
        balance=snapshot.balance,
        as_of=snapshot.as_of,
        source=snapshot.source,
        is_stale=(as_of - snapshot.as_of) > STALE_AFTER,
    )


def current_balance(session: Session, account_id: int) -> BalanceAt | None:
    """Today's balance. A thin alias, so no caller invents its own "latest" query."""
    return balance_in_force(session, account_id, dt.date.today())
