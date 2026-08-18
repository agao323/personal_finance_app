"""Ownership-adjusted money.

Two things live here and nowhere else:

1. **The stake lookup.** Every net worth figure is ownership-adjusted, and every
   ownership-adjusted figure comes through these helpers. If you find yourself writing
   ``SUM(balance)``, stop.
2. **Rounding.** :func:`adjust` is the only place in the codebase that rounds money.

See docs/ARCHITECTURE.md#users-and-ownership and #rounding.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.models.account import OwnershipStake

CENTS = Decimal("0.01")
FULL = Decimal("100.00")
ZERO = Decimal("0.00")


class OverlappingStakeError(ValueError):
    """Raised when a write would push stakes on one account past 100% on some date."""


def adjust(amount: Decimal, percentage: Decimal) -> Decimal:
    """Apply an ownership percentage to an amount, rounded half-up to cents.

    **The only rounding site in the codebase.** Rounding per account rather than on a
    total means the figure on screen always equals the sum of the rows above it;
    rounding at the end produces a dashboard whose numbers visibly do not add up,
    which destroys trust in every other number on the page.

    Half-up rather than Python's default banker's rounding: 50% of $1,234.57 is
    $617.285, and a household reading a statement expects $617.29. Banker's rounding
    would give $617.28 and the difference would be unexplainable.
    """
    return (amount * percentage / FULL).quantize(CENTS, rounding=ROUND_HALF_UP)


def _in_force_on(as_of: dt.date) -> ColumnElement[bool]:
    """SQL predicate: the stake row covers ``as_of``.

    Ranges are half-open — ``[effective_from, effective_to)`` — so the day a stake
    changes belongs to the new row, and closing one the same day another opens leaves
    neither a gap nor an overlap.
    """
    return and_(
        OwnershipStake.effective_from <= as_of,
        or_(OwnershipStake.effective_to.is_(None), OwnershipStake.effective_to > as_of),
    )


def effective_stake(
    session: Session, account_id: int, as_of: dt.date, user_id: int
) -> Decimal | None:
    """The percentage ``user_id`` owned of ``account_id`` on ``as_of``.

    Returns ``None`` when they held no stake that day. There is deliberately no
    "missing row means 100%" fallback: every account gets an explicit row at creation,
    so an absent row is a real answer rather than a default to guess at.
    """
    return session.execute(
        select(OwnershipStake.percentage).where(
            OwnershipStake.account_id == account_id,
            OwnershipStake.owner_user_id == user_id,
            _in_force_on(as_of),
        )
    ).scalar_one_or_none()


def household_stake(session: Session, account_id: int, as_of: dt.date) -> Decimal:
    """The total percentage owned by the household on ``as_of``.

    100 for a solely-owned account, less when part of the asset belongs to someone
    outside the household — a 50%-owned rental returns 50.
    """
    rows = session.execute(
        select(OwnershipStake.percentage).where(
            OwnershipStake.account_id == account_id, _in_force_on(as_of)
        )
    ).scalars()
    total = ZERO
    for percentage in rows:
        total += percentage
    return total


def _assert_within_limit(
    session: Session,
    account_id: int,
    percentage: Decimal,
    effective_from: dt.date,
    effective_to: dt.date | None,
    exclude_id: int | None = None,
) -> None:
    """Reject a stake that would push any covered date past 100%.

    Checked against every row whose range overlaps the new one rather than against a
    single date: a stake spanning years can collide with a short one anywhere inside
    it, and checking only the start date would miss that entirely.
    """
    conditions = [
        OwnershipStake.account_id == account_id,
        # Half-open overlap: [a, b) intersects [c, d) iff a < d and c < b, with NULL
        # standing in for "no end".
        or_(OwnershipStake.effective_to.is_(None), OwnershipStake.effective_to > effective_from),
    ]
    if effective_to is not None:
        conditions.append(OwnershipStake.effective_from < effective_to)
    if exclude_id is not None:
        conditions.append(OwnershipStake.id != exclude_id)

    for existing in session.execute(select(OwnershipStake).where(*conditions)).scalars():
        total = existing.percentage + percentage
        if total > FULL:
            raise OverlappingStakeError(
                f"account {account_id}: stakes overlapping "
                f"{effective_from}-{effective_to or 'open'} would total {total}%, over 100%"
            )


def create_initial_stake(
    session: Session,
    account_id: int,
    user_id: int,
    effective_from: dt.date,
    percentage: Decimal = FULL,
) -> OwnershipStake:
    """Open the first, open-ended stake for an account.

    Called at account creation without exception. This explicit row is what removes
    the "no row means fully owned" special case — ambiguous once a household has two
    people — from every lookup downstream.
    """
    _assert_within_limit(session, account_id, percentage, effective_from, None)

    stake = OwnershipStake(
        account_id=account_id,
        owner_user_id=user_id,
        percentage=percentage,
        effective_from=effective_from,
        effective_to=None,
    )
    session.add(stake)
    session.flush()
    return stake


def transition_stake(
    session: Session,
    account_id: int,
    user_id: int,
    percentage: Decimal,
    effective_from: dt.date,
) -> OwnershipStake:
    """Close the stake in force and open a new one, atomically.

    Both writes happen in the caller's transaction, so a failure leaves neither. A
    half-applied transition would either double-count the account for a period or drop
    it entirely, and both corrupt every historical figure that reads through the gap.

    The old row is closed *on* ``effective_from``. Ranges are half-open, so that date
    belongs to the new stake and the history has no gap and no overlap.
    """
    current = session.execute(
        select(OwnershipStake).where(
            OwnershipStake.account_id == account_id,
            OwnershipStake.owner_user_id == user_id,
            _in_force_on(effective_from),
        )
    ).scalar_one_or_none()

    if current is not None:
        if current.effective_from == effective_from:
            # Correcting a stake on the day it started: amend it rather than leave a
            # zero-length row behind, which no query could ever select.
            _assert_within_limit(
                session, account_id, percentage, effective_from, current.effective_to, current.id
            )
            current.percentage = percentage
            session.flush()
            return current
        current.effective_to = effective_from
        session.flush()

    _assert_within_limit(session, account_id, percentage, effective_from, None)

    stake = OwnershipStake(
        account_id=account_id,
        owner_user_id=user_id,
        percentage=percentage,
        effective_from=effective_from,
        effective_to=None,
    )
    session.add(stake)
    session.flush()
    return stake
