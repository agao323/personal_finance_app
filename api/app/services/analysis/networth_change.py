"""Why net worth moved: the change between two dates, attributed to accounts, with reasons.

Built from `net_worth.net_worth` at both dates in the same view, so every figure is one the
dashboard would show and nothing here rounds. **Per-account changes sum exactly to the
total change** — ARCHITECTURE's rounding rule exists so a figure equals the rows beneath it,
and an explanation whose parts did not add up to the change it explains would break the same
trust from the other side. A property test pins it.

A change has a reason, because the same number means different things:

- `opened` / `closed` — the account entered or left net worth in the window;
- `stake_changed` — the ownership share moved, so the same balance counts differently;
- `not_updated` — no balance was recorded in the window: a flat line that is carry-forward,
  not stability;
- `stale` — the balance used at the end is more than 90 days old;
- `value_changed` — a new balance was recorded and it differs.

Where an account's transfers are imported, `flows` separates money moved in or out from the
change in value. It is labelled an estimate: a flow can post on a different day from the
balance it affected.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot
from app.models.enums import AccountKind, CategoryKind
from app.models.transaction import Category, Transaction
from app.services.analysis.numbers import ZERO
from app.services.net_worth import AccountContribution, NetWorth, earliest_snapshot, net_worth

Reason = Literal["opened", "closed", "stake_changed", "not_updated", "stale", "value_changed"]


@dataclass(frozen=True)
class AccountChange:
    account_id: int
    name: str
    kind: AccountKind
    #: This account's share at each date; `None` when it was not part of net worth then.
    before: Decimal | None
    after: Decimal | None
    #: The effect on net worth: a larger liability is a negative change.
    change: Decimal
    reasons: list[Reason]
    #: Money moved into (+) or out of (-) the account in the window, when imported.
    flows: Decimal | None
    #: The full-balance change less flows: an estimate of the change in value.
    value_change_estimate: Decimal | None


@dataclass(frozen=True)
class NetWorthChange:
    start: NetWorth
    end: NetWorth
    accounts: list[AccountChange]
    earliest_snapshot: dt.date | None

    @property
    def change(self) -> Decimal:
        return self.end.net_worth - self.start.net_worth

    @property
    def by_kind(self) -> dict[AccountKind, Decimal]:
        totals: dict[AccountKind, Decimal] = {}
        for account in self.accounts:
            totals[account.kind] = totals.get(account.kind, ZERO) + account.change
        return totals

    @property
    def history_reaches_start(self) -> bool:
        return self.earliest_snapshot is not None and self.earliest_snapshot <= self.start.as_of


def _signed(contribution: AccountContribution | None) -> Decimal:
    """What an account adds to net worth: positive for an asset, negative for a liability."""
    if contribution is None:
        return ZERO
    if contribution.kind is AccountKind.LIABILITY:
        return -contribution.adjusted_balance
    return contribution.adjusted_balance


def _snapshots_between(session: Session, start: dt.date, end: dt.date) -> set[int]:
    rows = session.execute(
        select(BalanceSnapshot.account_id)
        .where(BalanceSnapshot.as_of > start, BalanceSnapshot.as_of <= end)
        .distinct()
    ).scalars()
    return set(rows)


def _flows(session: Session, start: dt.date, end: dt.date) -> dict[int, Decimal]:
    """Per account, money moved in or out in `(start, end]`: marked or categorised transfers."""
    rows = session.execute(
        select(Transaction.account_id, func.sum(Transaction.amount))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.posted_at > start,
            Transaction.posted_at <= end,
            or_(
                Transaction.transfer_group_id.is_not(None),
                Category.kind == CategoryKind.TRANSFER,
            ),
        )
        .group_by(Transaction.account_id)
    ).all()
    return {account_id: total for account_id, total in rows}


def explain(
    session: Session, start: dt.date, end: dt.date, viewer_id: int | None
) -> NetWorthChange:
    """Net worth at `start` and `end` in one view, and each account's part in the change."""
    before = net_worth(session, start, viewer_id)
    after = net_worth(session, end, viewer_id)
    was = {c.account_id: c for c in before.contributions}
    now = {c.account_id: c for c in after.contributions}
    ids = sorted(was.keys() | now.keys())
    accounts = {
        a.id: a for a in session.execute(select(Account).where(Account.id.in_(ids))).scalars()
    }
    updated = _snapshots_between(session, start, end)
    flows = _flows(session, start, end)

    changes: list[AccountChange] = []
    for account_id in ids:
        a, b = was.get(account_id), now.get(account_id)
        account = accounts[account_id]
        reasons: list[Reason] = []
        if a is None:
            reasons.append("opened")
        elif b is None:
            reasons.append("closed")
        else:
            if a.percentage != b.percentage:
                reasons.append("stake_changed")
            if account_id not in updated:
                reasons.append("not_updated")
            elif a.raw_balance != b.raw_balance:
                reasons.append("value_changed")
        if b is not None and b.is_stale:
            reasons.append("stale")

        flow = flows.get(account_id) if account.kind is not AccountKind.LIABILITY else None
        estimate = None
        if flow is not None and a is not None and b is not None:
            estimate = (b.raw_balance - a.raw_balance) - flow

        changes.append(
            AccountChange(
                account_id=account_id,
                name=account.name,
                kind=account.kind,
                before=a.adjusted_balance if a else None,
                after=b.adjusted_balance if b else None,
                change=_signed(b) - _signed(a),
                reasons=reasons,
                flows=flow,
                value_change_estimate=estimate,
            )
        )
    changes.sort(key=lambda c: (-abs(c.change), c.name))
    return NetWorthChange(
        start=before, end=after, accounts=changes, earliest_snapshot=earliest_snapshot(session)
    )
