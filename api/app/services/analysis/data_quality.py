"""How far the numbers can be trusted: stale balances, quiet imports, gaps in categorising,
and transfers nobody marked.

Asked before advice, not after. A recommendation built on a four-month-old balance, or on a
month whose card export was never imported, is the thing "no push to act on stale data"
exists to stop (docs/ADVISOR.md#advice-guardrails).

**Possible unmarked transfers are suggestions.** Marking a pair stays a person's decision
on `/transactions`; this reads, it does not mark. That is why it does not pull PRODUCT's
"automatic transfer-pair detection" forward. It is worth a warning all the same: a transfer
counted as spend inflates burn and makes runway read short.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot
from app.models.enums import CategoryKind
from app.models.transaction import Category, Transaction
from app.services.analysis.numbers import ZERO, ratio_bps
from app.services.balances import STALE_AFTER
from app.services.spend import expense_rows

#: The smallest amount considered for a transfer pair. Below it, coincidences dominate.
TRANSFER_MIN = Decimal("50.00")
#: How far apart the two sides of a transfer may post.
TRANSFER_MAX_DAYS = 3
#: How far back to look for unmarked pairs.
TRANSFER_LOOKBACK_DAYS = 90


@dataclass(frozen=True)
class AccountHealth:
    account: Account
    last_snapshot: dt.date | None
    balance_stale: bool
    last_transaction: dt.date | None

    @property
    def imports_transactions(self) -> bool:
        return self.last_transaction is not None


@dataclass(frozen=True)
class TransferPair:
    outflow: Transaction
    inflow: Transaction

    @property
    def days_apart(self) -> int:
        return abs((self.inflow.posted_at - self.outflow.posted_at).days)


@dataclass(frozen=True)
class Health:
    accounts: list[AccountHealth]
    earliest_snapshot: dt.date | None
    #: The last complete month, which the uncategorised figures describe.
    month: dt.date
    uncategorised_count: int
    uncategorised_spend: Decimal
    month_spend: Decimal
    pairs: list[TransferPair]

    @property
    def uncategorised_share_bps(self) -> int | None:
        return ratio_bps(self.uncategorised_spend, self.month_spend) if self.month_spend else None

    @property
    def stale_balance_count(self) -> int:
        return sum(1 for a in self.accounts if a.balance_stale)


def _last_complete_month(today: dt.date) -> tuple[dt.date, dt.date]:
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def possible_transfers(session: Session, start: dt.date, end: dt.date) -> list[TransferPair]:
    """Opposite amounts on two different accounts within a few days, neither marked.

    Each transaction joins at most one pair, closest dates first, so three candidates for
    one outflow produce one pair rather than three.
    """
    rows = list(
        session.execute(
            select(Transaction)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.posted_at >= start - dt.timedelta(days=TRANSFER_MAX_DAYS),
                Transaction.posted_at <= end,
                Transaction.transfer_group_id.is_(None),
                func.abs(Transaction.amount) >= TRANSFER_MIN,
                or_(Category.kind.is_(None), Category.kind != CategoryKind.TRANSFER),
            )
        ).scalars()
    )
    outflows = [t for t in rows if t.amount < 0]
    inflows: dict[Decimal, list[Transaction]] = {}
    for t in rows:
        if t.amount > 0:
            inflows.setdefault(t.amount, []).append(t)

    candidates: list[tuple[int, int, int, Transaction, Transaction]] = []
    for out in outflows:
        for into in inflows.get(-out.amount, []):
            days = abs((into.posted_at - out.posted_at).days)
            if into.account_id != out.account_id and days <= TRANSFER_MAX_DAYS:
                candidates.append((days, out.id, into.id, out, into))
    candidates.sort(key=lambda c: c[:3])

    used: set[int] = set()
    pairs: list[TransferPair] = []
    for _, out_id, in_id, out, into in candidates:
        if out_id in used or in_id in used:
            continue
        if max(out.posted_at, into.posted_at) < start:
            continue
        used.update((out_id, in_id))
        pairs.append(TransferPair(outflow=out, inflow=into))
    pairs.sort(key=lambda p: p.outflow.posted_at, reverse=True)
    return pairs


def health(session: Session, today: dt.date) -> Health:
    accounts = list(
        session.execute(
            select(Account)
            .where(or_(Account.closed_at.is_(None), Account.closed_at > today))
            .order_by(Account.kind, Account.name)
        ).scalars()
    )
    last_snapshot: dict[int, dt.date] = {
        account_id: day
        for account_id, day in session.execute(
            select(BalanceSnapshot.account_id, func.max(BalanceSnapshot.as_of))
            .where(BalanceSnapshot.as_of <= today)
            .group_by(BalanceSnapshot.account_id)
        ).all()
    }
    last_transaction: dict[int, dt.date] = {
        account_id: day
        for account_id, day in session.execute(
            select(Transaction.account_id, func.max(Transaction.posted_at))
            .where(Transaction.posted_at <= today)
            .group_by(Transaction.account_id)
        ).all()
    }

    start, end = _last_complete_month(today)
    uncategorised_count = 0
    uncategorised = ZERO
    total = ZERO
    for transaction, category in expense_rows(session, start, end):
        spend = -transaction.amount
        total += spend
        if category is None:
            uncategorised_count += 1
            uncategorised += spend

    return Health(
        accounts=[
            AccountHealth(
                account=account,
                last_snapshot=last_snapshot.get(account.id),
                balance_stale=(
                    account.id in last_snapshot and today - last_snapshot[account.id] > STALE_AFTER
                ),
                last_transaction=last_transaction.get(account.id),
            )
            for account in accounts
        ],
        earliest_snapshot=session.execute(select(func.min(BalanceSnapshot.as_of))).scalar(),
        month=start,
        uncategorised_count=uncategorised_count,
        uncategorised_spend=uncategorised,
        month_spend=total,
        pairs=possible_transfers(session, today - dt.timedelta(days=TRANSFER_LOOKBACK_DAYS), today),
    )
