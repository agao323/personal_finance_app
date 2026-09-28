"""The household's asset mix: each account split by class, drift from target, and cash drag.

Per scope, every asset account's **ownership-adjusted balance** (from the net worth service,
rounded once, per account) is divided by the allocation in force on `today` with
`ownership.split`, so an account's classes sum exactly to its figure and the totals by class
sum exactly to total assets. Nothing here rounds money a second time.

An account with no allocation recorded is **unknown** — its whole balance sits in the unknown
total and in no class. It is never folded into cash or anything else.

**Drift** is measured over the investable base: accounts with a recorded allocation plus cash
accounts. Property and vehicles are left out — the planning target mix has no place for a house,
and counting one would make every household look wildly over-weight in "other". Drift is each
class's actual share of that base less its target, in percentage points (as basis points), and
is not stated at all when half or more of what could be investable is unknown.

**Cash drag** is cash beyond the emergency fund: the active emergency-fund goal's months, or
six without one, times the last six complete months' average spending. Spending is never split
by ownership, so the burn is the household's in both scopes, as runway's is.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind, AssetClass, GoalKind, GoalStatus
from app.models.goal import Goal
from app.models.planning import PlanningAssumptions
from app.services import allocations
from app.services import net_worth as net_worth_service
from app.services import runway as runway_service
from app.services.analysis.numbers import ZERO, quantize_money, ratio_bps
from app.services.ownership import split

#: Months of spending held back as an emergency fund when no goal sets the number.
DEFAULT_FUND_MONTHS = Decimal("6")
BURN_WINDOW = 6
#: Classes the planning target mix covers. Real estate is not one of them.
TARGET_CLASSES = (
    AssetClass.US_EQUITY,
    AssetClass.INTL_EQUITY,
    AssetClass.BONDS,
    AssetClass.CASH,
    AssetClass.OTHER,
)
LABELS: dict[AssetClass, str] = {
    AssetClass.US_EQUITY: "US stocks",
    AssetClass.INTL_EQUITY: "international stocks",
    AssetClass.BONDS: "bonds",
    AssetClass.CASH: "cash",
    AssetClass.REAL_ESTATE: "real estate",
    AssetClass.OTHER: "other",
}
#: Drift is not stated when this share or more of the investable base is unknown.
UNKNOWN_TOO_MUCH_BPS = 5000


@dataclass(frozen=True)
class AccountMix:
    account_id: int
    name: str
    status: allocations.AllocationStatus
    #: When the allocation in force was entered; None when derived or unknown.
    entered_on: dt.date | None
    value: Decimal
    parts: dict[AssetClass, Decimal]
    stale: bool
    investable: bool


@dataclass(frozen=True)
class Drift:
    asset_class: AssetClass
    actual_bps: int
    target_bps: int

    @property
    def drift_bps(self) -> int:
        return self.actual_bps - self.target_bps


@dataclass(frozen=True)
class CashDrag:
    cash: Decimal
    fund_months: Decimal
    from_goal: bool
    monthly_burn: Decimal
    #: The emergency fund in dollars: fund months times the monthly burn, rounded once.
    fund_target: Decimal
    beyond: Decimal


@dataclass(frozen=True)
class Mix:
    as_of: dt.date
    accounts: list[AccountMix]
    by_class: dict[AssetClass, Decimal]
    unknown: Decimal
    total: Decimal
    investable: Decimal
    #: Drift from the target mix; empty when too much is unknown or nothing is investable.
    drift: list[Drift]
    drift_withheld: bool
    target_defaults: bool
    cash_drag: CashDrag | None
    stale: bool = field(default=False)


def _target(session: Session) -> tuple[dict[AssetClass, int], bool]:
    row = session.execute(
        select(PlanningAssumptions)
        .order_by(PlanningAssumptions.effective_from.desc(), PlanningAssumptions.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return {}, True
    pcts = {
        AssetClass.US_EQUITY: row.target_us_equity_pct,
        AssetClass.INTL_EQUITY: row.target_intl_equity_pct,
        AssetClass.BONDS: row.target_bonds_pct,
        AssetClass.CASH: row.target_cash_pct,
        AssetClass.OTHER: row.target_other_pct,
    }
    return {cls: int(pct.scaleb(2)) for cls, pct in pcts.items()}, row.is_default


def fund_months(session: Session, user_id: int) -> tuple[Decimal, bool]:
    """The active emergency-fund goal visible to `user_id`, or six months without one."""
    goal = session.execute(
        select(Goal)
        .where(
            Goal.kind == GoalKind.EMERGENCY_FUND,
            Goal.status == GoalStatus.ACTIVE,
            or_(Goal.owner_user_id.is_(None), Goal.owner_user_id == user_id),
        )
        .order_by(Goal.id)
        .limit(1)
    ).scalar_one_or_none()
    if goal is None or goal.target_months is None:
        return DEFAULT_FUND_MONTHS, False
    return goal.target_months, True


def mix(session: Session, today: dt.date, viewer_id: int | None, user_id: int) -> Mix:
    """The asset mix in one scope: `viewer_id` None is the household, else that member."""
    worth = net_worth_service.net_worth(session, today, viewer_id)
    accounts: list[AccountMix] = []
    for c in worth.contributions:
        if c.kind is AccountKind.LIABILITY:
            continue
        account = session.get_one(Account, c.account_id)
        current = allocations.allocation_for(session, account, today)
        if current.shares:
            classes = sorted(current.shares, key=list(AssetClass).index)
            parts = dict(
                zip(
                    classes,
                    split(c.adjusted_balance, [current.shares[cls] for cls in classes]),
                    strict=True,
                )
            )
        else:
            parts = {}
        entered = None
        if current.status == "recorded":
            entered = max(
                r.effective_from for r in allocations.in_force(session, account.id, today)
            )
        accounts.append(
            AccountMix(
                account_id=account.id,
                name=account.name,
                status=current.status,
                entered_on=entered,
                value=c.adjusted_balance,
                parts=parts,
                stale=c.is_stale,
                investable=current.status == "recorded"
                or (current.status == "derived" and AssetClass.CASH in current.shares),
            )
        )

    by_class = {cls: ZERO for cls in AssetClass}
    investable_by_class = {cls: ZERO for cls in AssetClass}
    for row in accounts:
        for cls, amount in row.parts.items():
            by_class[cls] += amount
            if row.investable:
                investable_by_class[cls] += amount
    unknown = sum((a.value for a in accounts if a.status == "unknown"), ZERO)
    total = sum((a.value for a in accounts), ZERO)
    investable = sum(investable_by_class.values(), ZERO)

    target, defaults = _target(session)
    withheld = (
        investable + unknown > 0
        and (ratio_bps(unknown, investable + unknown) or 0) >= UNKNOWN_TOO_MUCH_BPS
    )
    drift: list[Drift] = []
    if investable > 0 and target and not withheld:
        for cls in TARGET_CLASSES:
            drift.append(
                Drift(cls, ratio_bps(investable_by_class[cls], investable) or 0, target[cls])
            )

    months, from_goal = fund_months(session, user_id)
    burn, _, _ = runway_service.burn_window(session, BURN_WINDOW, today)
    cash = by_class[AssetClass.CASH]
    drag = None
    if burn > 0:
        fund = quantize_money(months * burn)
        drag = CashDrag(
            cash=cash,
            fund_months=months,
            from_goal=from_goal,
            monthly_burn=quantize_money(burn),
            fund_target=fund,
            beyond=max(cash - fund, ZERO),
        )

    return Mix(
        as_of=today,
        accounts=accounts,
        by_class=by_class,
        unknown=unknown,
        total=total,
        investable=investable,
        drift=drift,
        drift_withheld=withheld,
        target_defaults=defaults,
        cash_drag=drag,
        stale=any(a.stale for a in accounts),
    )
