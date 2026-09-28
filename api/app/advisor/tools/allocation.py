"""Allocation tool: the asset mix, account by account, against the plan (ticket 116).

`allocation_get` returns each asset account's ownership-adjusted value split by class, the
totals, what is unknown, drift from the planning target mix and cash beyond the emergency fund,
all from `services/analysis/allocation.py`. Each recorded allocation carries the date it was
entered, because markets move the real mix away from what was entered and the model must say
which figures are "as entered on" a date rather than today's.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.tools import REGISTRY, ToolArgs, ToolContext, ToolResult
from app.models.enums import AssetClass
from app.schemas.common import ViewScope, to_cents
from app.services.allocations import AllocationStatus
from app.services.analysis import allocation as allocation_analysis
from app.services.analysis.numbers import ratio_bps, tenths


class AllocationArgs(ToolArgs):
    view: ViewScope | None = Field(
        default=None,
        description="mine: your ownership share of each account. household: every stake. "
        "Defaults to the conversation's view.",
    )


class ClassPart(BaseModel):
    asset_class: AssetClass
    value_cents: int


class AccountMixRow(BaseModel):
    account_id: int
    name_text: str
    status: AllocationStatus = Field(
        description="recorded: entered by hand. derived: follows from the account type. "
        "unknown: nothing entered, so its value is in no class."
    )
    entered_on: dt.date | None = Field(
        description="When a recorded allocation was entered. Say 'as entered on' this date."
    )
    value_cents: int = Field(description="Ownership-adjusted, in this view.")
    parts: list[ClassPart] = Field(description="Sums exactly to value.")
    stale: bool


class ClassTotal(BaseModel):
    asset_class: AssetClass
    value_cents: int
    share_bps: int = Field(description="Of every asset in this view, unknown included.")


class DriftRow(BaseModel):
    asset_class: AssetClass
    actual_bps: int = Field(description="Share of the investable base.")
    target_bps: int
    drift_bps: int = Field(description="Actual less target, in percentage points.")


class CashDragRow(BaseModel):
    cash_cents: int
    fund_months_tenths: int
    fund_from_goal: bool = Field(
        description="True: the emergency-fund goal's months. False: six months, a default."
    )
    monthly_spending_cents: int = Field(description="The last six complete months' average.")
    fund_target_cents: int
    beyond_cents: int = Field(description="Cash beyond the fund. Zero when there is none.")


class AllocationResult(ToolResult):
    accounts: list[AccountMixRow]
    totals: list[ClassTotal]
    unknown_cents: int = Field(description="Value in accounts with no allocation entered.")
    unknown_share_bps: int | None
    total_cents: int
    investable_cents: int = Field(
        description="Accounts with a recorded allocation, and cash: what drift is measured on. "
        "Property and vehicles are left out."
    )
    drift: list[DriftRow]
    drift_withheld: bool = Field(
        description="True when half or more of the investable base is unknown: drift is not "
        "stated. Suggest entering the missing allocations."
    )
    target_defaults: bool = Field(description="True: the target mix is the planning default.")
    cash_drag: CashDragRow | None = Field(
        description="Null when there is no spending history to size the fund against."
    )


@REGISTRY.tool(
    "allocation_get",
    description=(
        "The asset mix: each asset account's value split by class, totals by class, what is "
        "unknown, drift from the planning target mix and cash beyond the emergency fund. Call "
        "it for asset allocation, rebalancing or idle cash. Recorded allocations are as "
        "entered on a date, not live: say so, and never fold unknown value into a class."
    ),
    label=lambda args: f"Asset allocation{f', {args.view}' if args.view else ''}",
)
def allocation_get(args: AllocationArgs, session: Session, ctx: ToolContext) -> AllocationResult:
    mix = allocation_analysis.mix(session, ctx.today, ctx.viewer_id(args.view), ctx.user_id)
    drag = mix.cash_drag
    return AllocationResult(
        as_of=ctx.today,
        view=args.view or ctx.view,
        stale=mix.stale or None,
        accounts=[
            AccountMixRow(
                account_id=a.account_id,
                name_text=a.name,
                status=a.status,
                entered_on=a.entered_on,
                value_cents=to_cents(a.value),
                parts=[
                    ClassPart(asset_class=cls, value_cents=to_cents(amount))
                    for cls, amount in a.parts.items()
                ],
                stale=a.stale,
            )
            for a in mix.accounts
        ],
        totals=[
            ClassTotal(
                asset_class=cls,
                value_cents=to_cents(amount),
                share_bps=ratio_bps(amount, mix.total) or 0,
            )
            for cls, amount in mix.by_class.items()
            if amount != 0
        ],
        unknown_cents=to_cents(mix.unknown),
        unknown_share_bps=ratio_bps(mix.unknown, mix.total),
        total_cents=to_cents(mix.total),
        investable_cents=to_cents(mix.investable),
        drift=[
            DriftRow(
                asset_class=d.asset_class,
                actual_bps=d.actual_bps,
                target_bps=d.target_bps,
                drift_bps=d.drift_bps,
            )
            for d in mix.drift
        ],
        drift_withheld=mix.drift_withheld,
        target_defaults=mix.target_defaults,
        cash_drag=(
            CashDragRow(
                cash_cents=to_cents(drag.cash),
                fund_months_tenths=tenths(drag.fund_months),
                fund_from_goal=drag.from_goal,
                monthly_spending_cents=to_cents(drag.monthly_burn),
                fund_target_cents=to_cents(drag.fund_target),
                beyond_cents=to_cents(drag.beyond),
            )
            if drag is not None
            else None
        ),
    )
