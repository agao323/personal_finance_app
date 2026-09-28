"""Balance tools: net worth, its history, accounts, an account's history, and runway.

Each calls the service the dashboard calls, with `today` from the turn. Net worth figures
come only from `services/net_worth`, which rounds once per account in `ownership.py`;
nothing here rounds money. See docs/ADVISOR.md#tool-catalog.

**Mine or household** is the `view` argument, defaulting to the conversation's. It changes
whose stake applies. It never changes spend or burn, which are not split by ownership.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.advisor.tools import (
    REGISTRY,
    Detail,
    Id,
    ToolArgs,
    ToolContext,
    ToolInputError,
    ToolResult,
)
from app.models.account import Account, BalanceSnapshot
from app.models.enums import AccountKind, AccountSubtype
from app.schemas.common import ViewScope, to_bps, to_cents
from app.services import accounts as account_service
from app.services import net_worth as net_worth_service
from app.services import runway as runway_service

#: The most points a series or history returns.
MAX_POINTS = 120
#: Daily points are only offered over spans this short.
MAX_DAILY_SPAN_DAYS = 92
#: The longest account history a single call may ask for.
MAX_HISTORY_DAYS = 3653

VIEW_DESCRIPTION = (
    "mine: your ownership share. household: every household member's shares together. "
    "Omit to use the conversation's view."
)


def _view(ctx: ToolContext, view: ViewScope | None) -> ViewScope:
    return view or ctx.view


def _not_after_today(ctx: ToolContext, day: dt.date, name: str) -> None:
    if day > ctx.today:
        raise ToolInputError(
            f"{name} ({day.isoformat()}) is after today ({ctx.today.isoformat()})."
        )


# ── networth_get ──────────────────────────────────────────────────────────────


class NetworthGetArgs(ToolArgs):
    view: ViewScope | None = Field(default=None, description=VIEW_DESCRIPTION)
    as_of: dt.date | None = Field(default=None, description="Defaults to today.")
    detail: Detail = Field(
        default=Detail.FULL, description="concise leaves out the per-account breakdown."
    )


class KindTotal(BaseModel):
    kind: AccountKind
    total_cents: int


class Contribution(BaseModel):
    account_id: int
    name_text: str
    kind: AccountKind
    subtype: AccountSubtype
    stake_bps: int
    balance_cents: int
    share_cents: int
    balance_as_of: dt.date
    stale: bool


class NetworthGetResult(ToolResult):
    net_worth_cents: int
    assets_cents: int
    liabilities_cents: int
    by_kind: list[KindTotal]
    stale_account_count: int
    accounts: list[Contribution] | None = None


def _names(session: Session, ids: list[int]) -> dict[int, Account]:
    if not ids:
        return {}
    return {a.id: a for a in session.execute(select(Account).where(Account.id.in_(ids))).scalars()}


@REGISTRY.tool(
    "networth_get",
    description=(
        "Ownership-adjusted net worth on one date: assets, liabilities, a total per account "
        "kind, and each account's share with how current its balance is. Use it for 'what is "
        "our net worth' or 'what is my share of the house'. For how net worth moved over time "
        "use networth_series, and for why it changed between two dates use "
        "networth_explain_change. Liabilities are positive numbers that net worth subtracts. "
        "A balance carried forward more than 90 days is marked stale."
    ),
    label=lambda args: "Net worth" + (f" as of {args.as_of}" if args.as_of else ""),
)
def networth_get(args: NetworthGetArgs, session: Session, ctx: ToolContext) -> NetworthGetResult:
    as_of = args.as_of or ctx.today
    _not_after_today(ctx, as_of, "as_of")
    view = _view(ctx, args.view)
    result = net_worth_service.net_worth(session, as_of, ctx.viewer_id(view))

    accounts = None
    if args.detail is Detail.FULL:
        names = _names(session, [c.account_id for c in result.contributions])
        accounts = [
            Contribution(
                account_id=c.account_id,
                name_text=names[c.account_id].name,
                kind=c.kind,
                subtype=names[c.account_id].subtype,
                stake_bps=to_bps(c.percentage),
                balance_cents=to_cents(c.raw_balance),
                share_cents=to_cents(c.adjusted_balance),
                balance_as_of=c.balance_as_of,
                stale=c.is_stale,
            )
            for c in result.contributions
        ]

    return NetworthGetResult(
        as_of=as_of,
        view=view,
        stale=result.stale_count > 0,
        net_worth_cents=to_cents(result.net_worth),
        assets_cents=to_cents(result.assets),
        liabilities_cents=to_cents(result.liabilities),
        by_kind=[
            KindTotal(kind=kind, total_cents=to_cents(total))
            for kind, total in sorted(result.by_kind.items())
        ],
        stale_account_count=result.stale_count,
        accounts=accounts,
    )


# ── networth_series ───────────────────────────────────────────────────────────


class NetworthSeriesArgs(ToolArgs):
    view: ViewScope | None = Field(default=None, description=VIEW_DESCRIPTION)
    start: dt.date = Field(description="The first point.")
    end: dt.date | None = Field(default=None, description="The last point. Defaults to today.")
    interval: Literal["month", "week", "day"] = Field(
        default="month", description="day is only allowed for spans of 92 days or less."
    )


class SeriesPoint(BaseModel):
    as_of: dt.date
    net_worth_cents: int
    assets_cents: int
    liabilities_cents: int
    stale_account_count: int


class Coverage(BaseModel):
    earliest_snapshot: dt.date | None
    starts_after_requested_start: bool = Field(
        description="The history does not reach back to `start`; earlier points are omitted."
    )


class NetworthSeriesResult(ToolResult):
    interval: str
    points: list[SeriesPoint]
    coverage: Coverage


def _point_count(start: dt.date, end: dt.date, interval: str) -> int:
    days = (end - start).days
    if interval == "day":
        return days + 1
    if interval == "week":
        return days // 7 + 2
    return (end.year - start.year) * 12 + (end.month - start.month) + 2


@REGISTRY.tool(
    "networth_series",
    description=(
        "Net worth at each point between two dates, each point computed with that date's "
        "balances and ownership stakes. Use it for trends: 'how has our net worth moved this "
        "year'. At most 120 points, so use month for long spans; day only for 92 days or less. "
        "Points before the first recorded balance are omitted, and coverage says so. Each "
        "point counts accounts whose balance is more than 90 days old."
    ),
    label=lambda args: f"Net worth from {args.start}" + (f" to {args.end}" if args.end else ""),
)
def networth_series(
    args: NetworthSeriesArgs, session: Session, ctx: ToolContext
) -> NetworthSeriesResult:
    end = args.end or ctx.today
    _not_after_today(ctx, end, "end")
    if args.start > end:
        raise ToolInputError("start must be on or before end.")
    if args.interval == "day" and (end - args.start).days > MAX_DAILY_SPAN_DAYS:
        raise ToolInputError("day is only allowed over 92 days or less; use week or month.")
    if _point_count(args.start, end, args.interval) > MAX_POINTS:
        raise ToolInputError(
            f"That would be more than {MAX_POINTS} points. Use a longer interval or a shorter span."
        )

    view = _view(ctx, args.view)
    earliest = net_worth_service.earliest_snapshot(session)
    series = net_worth_service.net_worth_series(
        session, args.start, end, args.interval, ctx.viewer_id(view)
    )
    return NetworthSeriesResult(
        as_of=end,
        view=view,
        stale=any(point.stale_count for point in series),
        interval=args.interval,
        points=[
            SeriesPoint(
                as_of=point.as_of,
                net_worth_cents=to_cents(point.net_worth),
                assets_cents=to_cents(point.assets),
                liabilities_cents=to_cents(point.liabilities),
                stale_account_count=point.stale_count,
            )
            for point in series
        ],
        coverage=Coverage(
            earliest_snapshot=earliest,
            starts_after_requested_start=earliest is None or earliest > args.start,
        ),
    )


# ── accounts_list ─────────────────────────────────────────────────────────────


class AccountsListArgs(ToolArgs):
    view: ViewScope | None = Field(default=None, description=VIEW_DESCRIPTION)
    include_closed: bool = Field(default=False, description="Also list closed accounts.")


class AccountRow(BaseModel):
    account_id: int
    name_text: str
    kind: AccountKind
    subtype: AccountSubtype
    closed_on: dt.date | None
    stake_bps: int | None
    balance_cents: int | None
    share_cents: int | None
    balance_as_of: dt.date | None
    stale: bool


class AccountsListResult(ToolResult):
    accounts: list[AccountRow]


@REGISTRY.tool(
    "accounts_list",
    description=(
        "Every account with its kind, full balance, your or the household's share, and the "
        "date that balance was recorded. Use it to find account ids and to answer 'what "
        "accounts do we have' or 'which balances are out of date'. Closed accounts are left "
        "out unless include_closed is true. An account with no balance yet shows none rather "
        "than zero."
    ),
    label=lambda args: "Accounts" + (" including closed" if args.include_closed else ""),
)
def accounts_list(args: AccountsListArgs, session: Session, ctx: ToolContext) -> AccountsListResult:
    view = _view(ctx, args.view)
    views = account_service.list_accounts(
        session, ctx.today, ctx.viewer_id(view), include_closed=args.include_closed
    )
    rows = [
        AccountRow(
            account_id=v.account.id,
            name_text=v.account.name,
            kind=v.account.kind,
            subtype=v.account.subtype,
            closed_on=v.account.closed_at,
            stake_bps=to_bps(v.percentage) if v.percentage is not None else None,
            balance_cents=to_cents(v.balance.balance) if v.balance else None,
            share_cents=to_cents(v.adjusted) if v.adjusted is not None else None,
            balance_as_of=v.balance.as_of if v.balance else None,
            stale=bool(v.balance and v.balance.is_stale),
        )
        for v in views
    ]
    return AccountsListResult(
        as_of=ctx.today, view=view, stale=any(r.stale for r in rows), accounts=rows
    )


# ── accounts_history ──────────────────────────────────────────────────────────


class AccountsHistoryArgs(ToolArgs):
    account_id: Id = Field(description="From accounts_list.")
    start: dt.date | None = Field(default=None, description="Defaults to the first balance.")
    end: dt.date | None = Field(default=None, description="Defaults to today.")


class Snapshot(BaseModel):
    as_of: dt.date
    balance_cents: int


class Stake(BaseModel):
    owner: Literal["you", "another household member"]
    stake_bps: int
    effective_from: dt.date
    effective_to: dt.date | None


class AccountsHistoryResult(ToolResult):
    account_id: int
    name_text: str
    kind: AccountKind
    subtype: AccountSubtype
    closed_on: dt.date | None
    snapshots: list[Snapshot]
    downsampled_to_month_ends: bool
    stakes: list[Stake]

    def row_count(self) -> int:
        return len(self.snapshots)


def _month_ends(rows: list[BalanceSnapshot]) -> list[BalanceSnapshot]:
    """The last snapshot in each month, oldest first."""
    last: dict[tuple[int, int], BalanceSnapshot] = {}
    for row in rows:
        last[(row.as_of.year, row.as_of.month)] = row
    return list(last.values())


@REGISTRY.tool(
    "accounts_history",
    description=(
        "One account's recorded balances over time, and every ownership stake it has had with "
        "the dates each applied. Balances are the full account value, before any stake. Use it "
        "for 'how has the brokerage grown' or 'when did the stake on the house change'. At most "
        "120 balances; longer histories are cut to the last balance in each month. For the "
        "household total over time use networth_series instead."
    ),
    shape="rows",
    label=lambda args: f"Balance history of account {args.account_id}",
)
def accounts_history(
    args: AccountsHistoryArgs, session: Session, ctx: ToolContext
) -> AccountsHistoryResult:
    account = session.get(Account, args.account_id)
    if account is None:
        raise ToolInputError(f"No account with id {args.account_id}. Use accounts_list for ids.")
    end = args.end or ctx.today
    _not_after_today(ctx, end, "end")
    first = session.execute(
        select(func.min(BalanceSnapshot.as_of)).where(BalanceSnapshot.account_id == account.id)
    ).scalar_one_or_none()
    start = args.start or first or end
    if start > end:
        raise ToolInputError("start must be on or before end.")
    if (end - start).days > MAX_HISTORY_DAYS:
        raise ToolInputError("A history can span at most ten years.")

    rows = [
        row
        for row in account_service.snapshot_history(session, account.id)
        if start <= row.as_of <= end
    ]
    downsampled = len(rows) > MAX_POINTS
    if downsampled:
        rows = _month_ends(rows)[-MAX_POINTS:]

    return AccountsHistoryResult(
        as_of=end,
        account_id=account.id,
        name_text=account.name,
        kind=account.kind,
        subtype=account.subtype,
        closed_on=account.closed_at,
        snapshots=[Snapshot(as_of=r.as_of, balance_cents=to_cents(r.balance)) for r in rows],
        downsampled_to_month_ends=downsampled,
        stakes=[
            Stake(
                # Never a name or an id: the model needs to know whose share it is, and
                # nothing more about who holds it.
                owner="you" if s.owner_user_id == ctx.user_id else "another household member",
                stake_bps=to_bps(s.percentage),
                effective_from=s.effective_from,
                effective_to=s.effective_to,
            )
            for s in account_service.stake_history(session, account.id)
        ],
    )


# ── runway_get ────────────────────────────────────────────────────────────────


class RunwayGetArgs(ToolArgs):
    view: ViewScope | None = Field(
        default=None,
        description=(
            "Changes whose share of liquid assets counts. Burn is the household's spending "
            "either way. Omit to use the conversation's view."
        ),
    )


class BurnWindow(BaseModel):
    months: int
    average_monthly_spend_cents: int
    runway_months_tenths: int | None = Field(description="None when there was no spending.")
    months_counted: int
    months_excluded_as_outliers: int


class RunwayGetResult(ToolResult):
    liquid_assets_cents: int
    windows: list[BurnWindow]
    current_month_excluded: bool


def _tenths(months: float | None) -> int | None:
    """The service's ratio to tenths of a month, for display only; never used in arithmetic."""
    if months is None:
        return None
    return int(Decimal(str(months)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP).scaleb(1))


@REGISTRY.tool(
    "runway_get",
    description=(
        "Months of runway: liquid assets divided by average monthly spending over the last 3, "
        "6 and 12 complete months. Spending is gross, excluding transfers, and income is not "
        "netted, so it answers 'how long if income stopped'. The current month is left out "
        "because it is incomplete; months with no transactions are skipped; a month over three "
        "times the median is excluded as an outlier. For spending detail use "
        "spend_by_category."
    ),
    label=lambda args: "Runway",
)
def runway_get(args: RunwayGetArgs, session: Session, ctx: ToolContext) -> RunwayGetResult:
    view = _view(ctx, args.view)
    result = runway_service.runway(session, today=ctx.today, viewer_id=ctx.viewer_id(view))
    return RunwayGetResult(
        as_of=ctx.today,
        view=view,
        liquid_assets_cents=to_cents(result.liquid_assets),
        windows=[
            BurnWindow(
                months=w.months,
                average_monthly_spend_cents=to_cents(w.average_monthly_spend),
                runway_months_tenths=_tenths(w.months_of_runway),
                months_counted=w.months_counted,
                months_excluded_as_outliers=w.months_excluded_as_outliers,
            )
            for w in result.windows
        ],
        current_month_excluded=result.partial_month_excluded,
    )
