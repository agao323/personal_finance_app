"""Ownership-adjusted net worth.

The single calculation every endpoint and chart calls. There is no other code path
that sums balances — see docs/ARCHITECTURE.md#ownership-is-applied-in-exactly-one-place.

The load-bearing subtlety is **"in force on ``as_of``"**: asking for net worth on a past
date must use that date's balances *and* that date's ownership stakes, never today's.
Get it wrong and every point on the history chart except the last is wrong, and it
looks entirely plausible.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind
from app.services.balances import balance_in_force
from app.services.ownership import adjust, effective_stake, household_stake

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class AccountContribution:
    """One account's ownership-adjusted contribution, and where it came from."""

    account_id: int
    kind: AccountKind
    raw_balance: Decimal
    """Full balance, before the ownership stake. Positive for liabilities too."""
    adjusted_balance: Decimal
    """After the stake, rounded. Liabilities are still positive here."""
    percentage: Decimal
    balance_as_of: dt.date
    """The snapshot's date, which may predate ``as_of`` — see carry-forward."""
    is_stale: bool


@dataclass(frozen=True)
class NetWorth:
    as_of: dt.date
    viewer_id: int | None
    """``None`` means the household total across every stake."""

    net_worth: Decimal
    assets: Decimal
    liabilities: Decimal
    """Positive. ``net_worth`` is ``assets - liabilities``."""

    by_kind: dict[AccountKind, Decimal] = field(default_factory=dict)
    contributions: list[AccountContribution] = field(default_factory=list)
    stale_account_ids: list[int] = field(default_factory=list)

    @property
    def stale_count(self) -> int:
        return len(self.stale_account_ids)


def net_worth(session: Session, as_of: dt.date, viewer_id: int | None = None) -> NetWorth:
    """Ownership-adjusted net worth on ``as_of``.

    ``viewer_id`` selects whose share: a user id applies that user's stake, ``None``
    sums every stake on the account. A 50%-owned rental contributes half for the
    viewer and all of it for the household.

    Accounts are excluded — not counted as zero — when they had no snapshot by
    ``as_of``, when they closed on or before it, or when the viewer held no stake that
    day. Zero would be a claim about the balance; exclusion is the truth, which is
    that the account was not part of this net worth on that date.

    Stale balances are *included* and reported. Dropping them would make net worth
    silently fall the day a snapshot aged past the carry-forward cap, which is worse
    than showing a number with a warning attached.
    """
    contributions: list[AccountContribution] = []

    for account in session.execute(select(Account)).scalars():
        contribution = _contribution(session, account, as_of, viewer_id)
        if contribution is not None:
            contributions.append(contribution)

    assets = ZERO
    liabilities = ZERO
    by_kind: dict[AccountKind, Decimal] = {}

    for item in contributions:
        by_kind[item.kind] = by_kind.get(item.kind, ZERO) + item.adjusted_balance
        if item.kind is AccountKind.LIABILITY:
            liabilities += item.adjusted_balance
        else:
            assets += item.adjusted_balance

    return NetWorth(
        as_of=as_of,
        viewer_id=viewer_id,
        net_worth=assets - liabilities,
        assets=assets,
        liabilities=liabilities,
        by_kind=by_kind,
        contributions=contributions,
        stale_account_ids=[c.account_id for c in contributions if c.is_stale],
    )


def _contribution(
    session: Session, account: Account, as_of: dt.date, viewer_id: int | None
) -> AccountContribution | None:
    """One account's share, or ``None`` when it does not belong in this total."""
    # balance_in_force already excludes accounts closed on or before as_of and
    # accounts with no snapshot by then, and reports carry-forward staleness.
    balance = balance_in_force(session, account.id, as_of)
    if balance is None:
        return None

    if viewer_id is None:
        percentage = household_stake(session, account.id, as_of)
    else:
        stake = effective_stake(session, account.id, as_of, viewer_id)
        if stake is None:
            # The viewer held no stake that day. Not a zero balance — not their
            # account at all, on that date.
            return None
        percentage = stake

    if percentage == ZERO:
        return None

    return AccountContribution(
        account_id=account.id,
        kind=account.kind,
        raw_balance=balance.balance,
        # Rounded here, per account, by the one helper allowed to round. The total is
        # then the sum of these, so the figure on screen equals the sum of its rows.
        adjusted_balance=adjust(balance.balance, percentage),
        percentage=percentage,
        balance_as_of=balance.as_of,
        is_stale=balance.is_stale,
    )
