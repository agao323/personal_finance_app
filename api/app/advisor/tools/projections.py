"""Projection tools: retirement as a band, and one change at a time (ticket 118).

`projection_retirement` returns the engine's band — success across the withdrawal rates and a
range of retirement years, the earliest year reaching 90% — with every assumption, the version
of the assumptions it used, and the data it had to leave out. `projection_what_if` runs the
engine twice, on the same return paths, with one input changed, and returns both and the
difference, so the model quotes a computed change rather than estimating one.

When something a projection needs is missing — the returns table, a birth year, a year of
spending, any allocation or tax treatment — the result says which, with the limitation kind to
note, and carries no figures at all.
"""

from __future__ import annotations

import enum
from dataclasses import replace
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.tools import REGISTRY, ToolArgs, ToolContext, ToolInputError, ToolResult
from app.schemas.advisor import LimitationKind
from app.schemas.common import ViewScope, from_cents, to_cents
from app.services.analysis import projections as engine
from app.services.analysis.numbers import quantize_money

Unavailable = Literal[
    "no_returns_table", "no_birth_year", "no_spending_history", "no_allocation", "no_tax_treatment"
]
_LIMITATION: dict[str, LimitationKind] = {
    "no_returns_table": LimitationKind.PROJECTIONS,
    "no_birth_year": LimitationKind.PROJECTIONS,
    "no_spending_history": LimitationKind.TRANSACTION_COVERAGE,
    "no_allocation": LimitationKind.HOLDINGS,
    "no_tax_treatment": LimitationKind.TAX_TREATMENT,
}
#: A year's spending at most $1M; a retirement year at most sixty years out.
MAX_SPEND_CENTS = 100_000_000
MAX_YEARS_OUT = 60


class RateRow(BaseModel):
    rate_bps: int = Field(description="The withdrawal rate: a share of the portfolio a year.")
    historical_success_bps: int = Field(description="Share of historical sequences that lasted.")
    bootstrap_success_bps: int = Field(description="Share of shuffled sequences that lasted.")
    median_withdrawal_cents: int = Field(
        description="A year's spending this rate supports on the median path, in today's dollars."
    )


class YearRow(BaseModel):
    year: int
    age: int
    historical_success_bps: int
    bootstrap_success_bps: int


class BucketRow(BaseModel):
    bucket: engine.Bucket
    balance_cents: int


class AccountGap(BaseModel):
    account_id: int
    name_text: str


class Band(BaseModel):
    """One run of the engine: always a band, never one figure."""

    rates_at_year: int = Field(description="The retirement year the rate band is measured at.")
    by_rate: list[RateRow] = Field(min_length=2)
    by_year: list[YearRow] = Field(min_length=1)
    earliest_year: int | None = Field(
        description="The first retirement year reaching 90% on both historical and shuffled "
        "sequences. Null: none by 70."
    )


class ProjectionResult(ToolResult):
    unavailable: Unavailable | None = Field(
        default=None,
        description="Set when nothing could be projected: say why, note limitation_kind, and "
        "give no figures.",
    )
    limitation_kind: LimitationKind | None = None
    band: Band | None = None
    birth_year: int | None = None
    target_retirement_year: int | None = None
    buckets: list[BucketRow] = Field(default_factory=list)
    annual_spending_cents: int | None = None
    healthcare_pre65_cents: int | None = None
    annual_contribution_cents: int | None = None
    contribution_source: Literal["trailing_12_months", "override"] | None = None
    tax_deferred_rate_bps: int | None = None
    end_age: int | None = None
    assumptions_id: int | None = Field(
        default=None, description="The version of the planning assumptions used. Name it."
    )
    returns_source_text: str | None = None
    historical_paths: int | None = None
    bootstrap_paths: int | None = None
    unknown_allocation_cents: int | None = Field(
        default=None, description="Left out: accounts with no allocation entered."
    )
    education_cents: int | None = Field(default=None, description="Left out: 529 money.")
    tax_treatment_assumed: list[AccountGap] = Field(
        default_factory=list,
        description="Accounts whose tax treatment was never recorded; the type's default stood in.",
    )
    limitations: list[str] = Field(default_factory=list, description="Say these with the result.")


def _band(result: engine.Projection) -> Band:
    return Band(
        rates_at_year=result.rates_at_year,
        by_rate=[
            RateRow(
                rate_bps=r.rate_bps,
                historical_success_bps=r.historical_success_bps,
                bootstrap_success_bps=r.bootstrap_success_bps,
                median_withdrawal_cents=to_cents(r.median_withdrawal),
            )
            for r in result.by_rate
        ],
        by_year=[
            YearRow(
                year=y.year,
                age=y.age,
                historical_success_bps=y.historical_success_bps,
                bootstrap_success_bps=y.bootstrap_success_bps,
            )
            for y in result.by_year
        ],
        earliest_year=result.earliest_year,
    )


def _unavailable(error: engine.ProjectionUnavailableError, ctx: ToolContext) -> ProjectionResult:
    return ProjectionResult(
        as_of=ctx.today,
        unavailable=error.reason,
        limitation_kind=_LIMITATION[error.reason],
        limitations=[str(error)],
    )


def _full(result: engine.Projection, ctx: ToolContext, view: ViewScope | None) -> ProjectionResult:
    plan = result.plan
    return ProjectionResult(
        as_of=ctx.today,
        view=view or ctx.view,
        band=_band(result),
        birth_year=plan.birth_year,
        target_retirement_year=plan.target_retirement_year,
        buckets=[
            BucketRow(bucket=b, balance_cents=to_cents(plan.balances.get(b, Decimal(0))))
            for b in engine.BUCKETS
        ],
        annual_spending_cents=to_cents(plan.annual_spending),
        healthcare_pre65_cents=to_cents(plan.healthcare_pre65),
        annual_contribution_cents=to_cents(plan.annual_contribution),
        contribution_source=plan.contribution_source,
        tax_deferred_rate_bps=int(plan.tax_deferred_rate * 10000),
        end_age=plan.end_age,
        assumptions_id=plan.assumptions_id,
        returns_source_text=result.returns_source,
        historical_paths=result.historical_paths,
        bootstrap_paths=result.bootstrap_paths,
        unknown_allocation_cents=to_cents(plan.excluded_unknown),
        education_cents=to_cents(plan.excluded_education),
        tax_treatment_assumed=[
            AccountGap(account_id=i, name_text=name) for i, name in plan.defaulted_treatment
        ],
        limitations=result.limitations,
    )


def _check_year(year: int | None, ctx: ToolContext) -> None:
    if year is not None and not ctx.today.year < year <= ctx.today.year + MAX_YEARS_OUT:
        raise ToolInputError(
            f"retire_year must be after {ctx.today.year} and within {MAX_YEARS_OUT} years."
        )


# ── projection_retirement ─────────────────────────────────────────────────────


class RetirementArgs(ToolArgs):
    view: ViewScope | None = Field(
        default=None,
        description="household: every stake, the usual choice for a joint plan. mine: your "
        "share. Defaults to the conversation's view.",
    )
    retire_year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
        description="The retirement year asked about. Defaults to the profile's target.",
    )
    annual_spend_cents: int | None = Field(
        default=None,
        ge=0,
        le=MAX_SPEND_CENTS,
        description="A year's spending in retirement, in today's dollars. Defaults to the last "
        "twelve months'.",
    )


@REGISTRY.tool(
    "projection_retirement",
    description=(
        "Whether and when retirement works: success across withdrawal rates and across "
        "retirement years, on historical and shuffled return sequences, with taxable, "
        "tax-deferred and Roth money kept apart. Call it for any retirement or FIRE question. "
        "It is a band: never turn it into one number, name the assumptions and their version, "
        "and say what it leaves out."
    ),
    label=lambda args: (
        f"Retirement projection{f', retiring {args.retire_year}' if args.retire_year else ''}"
    ),
)
def projection_retirement(
    args: RetirementArgs, session: Session, ctx: ToolContext
) -> ProjectionResult:
    _check_year(args.retire_year, ctx)
    try:
        table = engine.returns_table()
        plan = engine.plan_for(
            session,
            ctx.today,
            ctx.user_id,
            ctx.viewer_id(args.view),
            annual_spending=(
                None if args.annual_spend_cents is None else from_cents(args.annual_spend_cents)
            ),
            target_retirement_year=args.retire_year,
        )
    except engine.ProjectionUnavailableError as error:
        return _unavailable(error, ctx)
    return _full(engine.project(plan, table), ctx, args.view)


# ── projection_what_if ────────────────────────────────────────────────────────


class Change(enum.StrEnum):
    EXTRA_MONTHLY_SAVING = "extra_monthly_saving"
    SPEND_CHANGE_BPS = "spend_change_bps"
    RETIRE_YEAR_SHIFT = "retire_year_shift"


#: Each change's bounds, checked after the schema's outer ones.
_BOUNDS: dict[Change, tuple[int, int, str]] = {
    Change.EXTRA_MONTHLY_SAVING: (-1_000_000, 1_000_000, "cents a month, up to $10,000 either way"),
    Change.SPEND_CHANGE_BPS: (-5000, 5000, "basis points, up to 50% either way"),
    Change.RETIRE_YEAR_SHIFT: (-15, 15, "years, up to 15 either way"),
}


class WhatIfArgs(ToolArgs):
    change: Change = Field(
        description="extra_monthly_saving: cents more (or less) saved each month. "
        "spend_change_bps: spending up or down by basis points (-1000 is 10% less). "
        "retire_year_shift: years later (or earlier, negative)."
    )
    value: int = Field(ge=-1_000_000, le=1_000_000, description="The size of the change.")
    view: ViewScope | None = Field(
        default=None, description="household or mine. Defaults to the conversation's view."
    )


class Differences(BaseModel):
    earliest_year_change: int | None = Field(
        description="Scenario's earliest 90% year less the base's. Negative: sooner. Null when "
        "either reaches 90% in no year."
    )
    success_change_bps: list[RateRow] = Field(
        description="Per withdrawal rate, the scenario's success less the base's. "
        "median_withdrawal is the change in the spending it supports."
    )


class WhatIfResult(ToolResult):
    unavailable: Unavailable | None = None
    limitation_kind: LimitationKind | None = None
    change: Change
    value: int
    base: Band | None = None
    scenario: Band | None = None
    base_annual_contribution_cents: int | None = None
    scenario_annual_contribution_cents: int | None = None
    base_annual_spending_cents: int | None = None
    scenario_annual_spending_cents: int | None = None
    base_retire_year: int | None = Field(default=None, description="Where the rate band sits.")
    scenario_retire_year: int | None = None
    differences: Differences | None = None
    assumptions_id: int | None = None
    limitations: list[str] = Field(default_factory=list, description="Say these with the result.")


def _scenario(
    plan: engine.Plan, change: Change, value: int, base: engine.Projection
) -> engine.Plan:
    if change is Change.EXTRA_MONTHLY_SAVING:
        extra = from_cents(value) * 12
        return replace(
            plan,
            annual_contribution=max(plan.annual_contribution + extra, Decimal(0)),
            contribution_source="override",
        )
    if change is Change.SPEND_CHANGE_BPS:
        factor = 1 + Decimal(value) / 10000
        return replace(plan, annual_spending=quantize_money(plan.annual_spending * factor))
    return replace(plan, target_retirement_year=base.rates_at_year + value)


@REGISTRY.tool(
    "projection_what_if",
    description=(
        "One change to the retirement projection — save more or less each month, spend more or "
        "less, retire earlier or later — run against the same return sequences as the base. "
        "Returns both bands and the difference, computed. Call it for 'what if we…' questions "
        "and quote the difference it gives rather than estimating one."
    ),
    label=lambda args: f"What if: {args.change.value.replace('_', ' ')} {args.value}",
)
def projection_what_if(args: WhatIfArgs, session: Session, ctx: ToolContext) -> WhatIfResult:
    low, high, unit = _BOUNDS[args.change]
    if not low <= args.value <= high:
        raise ToolInputError(f"{args.change.value} takes {unit}.")
    try:
        table = engine.returns_table()
        plan = engine.plan_for(session, ctx.today, ctx.user_id, ctx.viewer_id(args.view))
    except engine.ProjectionUnavailableError as error:
        gap = _unavailable(error, ctx)
        return WhatIfResult(
            as_of=ctx.today,
            change=args.change,
            value=args.value,
            unavailable=gap.unavailable,
            limitation_kind=gap.limitation_kind,
        )
    base = engine.project(plan, table)
    changed = _scenario(plan, args.change, args.value, base)
    scenario = engine.project(changed, table)
    earliest = (
        scenario.earliest_year - base.earliest_year
        if scenario.earliest_year is not None and base.earliest_year is not None
        else None
    )
    return WhatIfResult(
        as_of=ctx.today,
        view=args.view or ctx.view,
        change=args.change,
        value=args.value,
        base=_band(base),
        scenario=_band(scenario),
        base_annual_contribution_cents=to_cents(plan.annual_contribution),
        scenario_annual_contribution_cents=to_cents(changed.annual_contribution),
        base_annual_spending_cents=to_cents(plan.annual_spending),
        scenario_annual_spending_cents=to_cents(changed.annual_spending),
        base_retire_year=base.rates_at_year,
        scenario_retire_year=scenario.rates_at_year,
        assumptions_id=plan.assumptions_id,
        limitations=base.limitations,
        differences=Differences(
            earliest_year_change=earliest,
            success_change_bps=[
                RateRow(
                    rate_bps=s.rate_bps,
                    historical_success_bps=s.historical_success_bps - b.historical_success_bps,
                    bootstrap_success_bps=s.bootstrap_success_bps - b.bootstrap_success_bps,
                    median_withdrawal_cents=to_cents(s.median_withdrawal - b.median_withdrawal),
                )
                for s, b in zip(scenario.by_rate, base.by_rate, strict=True)
            ],
        ),
    )
