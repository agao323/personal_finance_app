"""Goal and planning tools: what the household is aiming for, and the assumptions it states.

Ticket 111. So advice can be measured against the household's own targets and assumptions
instead of defaults — and so an answer can say which ones it used.

- `goals_list` — the goals the person can see: the household's and their own.
- `goals_evaluate` — one goal's progress, or every active goal's, computed by
  `services/analysis/goals.py` (each goal in its own scope, whoever asks).
- `planning_profile` — the person's birth and retirement years, and the assumptions in force,
  flagged `defaults` when nobody has set them.

Goal names are typed by members and reach the model as `name_text`, sanitised like every name.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.advisor.tools import (
    REGISTRY,
    Id,
    NoArgs,
    ToolArgs,
    ToolContext,
    ToolInputError,
    ToolResult,
)
from app.models.enums import GoalKind, GoalStatus, RiskTolerance
from app.models.goal import Goal
from app.models.planning import MemberProfile, PlanningAssumptions
from app.models.transaction import Category
from app.schemas.common import ViewScope, to_cents
from app.services.analysis import goals as goal_analysis
from app.services.analysis.numbers import tenths


def _visible(session: Session, user_id: int, active_only: bool) -> list[Goal]:
    query = select(Goal).where(or_(Goal.owner_user_id.is_(None), Goal.owner_user_id == user_id))
    if active_only:
        query = query.where(Goal.status == GoalStatus.ACTIVE)
    return list(session.execute(query.order_by(Goal.id)).scalars())


class GoalRow(BaseModel):
    goal_id: int
    kind: GoalKind
    name_text: str
    view: ViewScope = Field(description="household: shared. mine: the asker's own goal.")
    status: GoalStatus
    category_name_text: str | None = None
    target_cents: int | None = Field(
        default=None, description="A savings target's total, or a spending limit per month."
    )
    target_months_tenths: int | None = None
    target_date: dt.date | None = None
    account_ids: list[int]


def _row(session: Session, goal: Goal) -> GoalRow:
    category = session.get(Category, goal.category_id) if goal.category_id else None
    return GoalRow(
        goal_id=goal.id,
        kind=goal.kind,
        name_text=goal.name,
        view=ViewScope.HOUSEHOLD if goal.owner_user_id is None else ViewScope.MINE,
        status=goal.status,
        category_name_text=category.name if category else None,
        target_cents=to_cents(goal.target_amount) if goal.target_amount is not None else None,
        target_months_tenths=tenths(goal.target_months) if goal.target_months is not None else None,
        target_date=goal.target_date,
        account_ids=[link.account_id for link in goal.links],
    )


# ── goals_list ────────────────────────────────────────────────────────────────


class GoalsListResult(ToolResult):
    goals: list[GoalRow]


@REGISTRY.tool(
    "goals_list",
    description=(
        "The household's goals and the asker's own: spending limits per category, emergency "
        "funds in months of spending, savings targets by a date. Call it whenever a question "
        "is about saving, spending discipline, affording something or being on track. For "
        "how a goal stands today use goals_evaluate."
    ),
    label=lambda args: "Goals",
)
def goals_list(args: NoArgs, session: Session, ctx: ToolContext) -> GoalsListResult:
    goals = _visible(session, ctx.user_id, active_only=False)
    return GoalsListResult(as_of=ctx.today, goals=[_row(session, goal) for goal in goals])


# ── goals_evaluate ────────────────────────────────────────────────────────────


class GoalsEvaluateArgs(ToolArgs):
    goal_id: Id | None = Field(
        default=None, description="One goal from goals_list. Omit for every active goal."
    )


class GoalProgressRow(BaseModel):
    goal: GoalRow
    on_track: bool
    stale: bool = Field(description="A balance behind this is more than 90 days old.")
    month_to_date_cents: int | None = Field(default=None, description="Spending limits.")
    last_month_cents: int | None = Field(default=None, description="Spending limits.")
    runway_months_tenths: int | None = Field(default=None, description="Emergency funds.")
    saved_cents: int | None = Field(default=None, description="Savings targets.")
    remaining_cents: int | None = None
    monthly_needed_cents: int | None = Field(
        default=None, description="Still to save each month to reach the target by its date."
    )
    progress_bps: int | None = Field(
        default=None,
        description="Saved as a share of the target, or spent as a share of the limit.",
    )


class GoalsEvaluateResult(ToolResult):
    goals: list[GoalProgressRow]


def _cents(value: Decimal | None) -> int | None:
    return None if value is None else to_cents(value)


@REGISTRY.tool(
    "goals_evaluate",
    description=(
        "How a goal stands today: spending this month against a limit, cash runway against an "
        "emergency fund's months, or a savings target's balance, what remains, and the monthly "
        "amount still needed by its date — each with whether it is on track. Omit goal_id for "
        "every active goal. Use it before advising anything a goal bears on."
    ),
    label=lambda args: f"Goal progress{f', goal {args.goal_id}' if args.goal_id else ''}",
)
def goals_evaluate(
    args: GoalsEvaluateArgs, session: Session, ctx: ToolContext
) -> GoalsEvaluateResult:
    if args.goal_id is None:
        goals = _visible(session, ctx.user_id, active_only=True)
    else:
        goals = [
            g for g in _visible(session, ctx.user_id, active_only=False) if g.id == args.goal_id
        ]
        if not goals:
            raise ToolInputError(f"No goal {args.goal_id} that you can see. Call goals_list.")
    rows = []
    for goal in goals:
        result = goal_analysis.progress(session, goal, ctx.today)
        rows.append(
            GoalProgressRow(
                goal=_row(session, goal),
                on_track=result.on_track,
                stale=result.stale,
                month_to_date_cents=_cents(result.month_to_date),
                last_month_cents=_cents(result.last_month),
                runway_months_tenths=result.runway_months_tenths,
                saved_cents=_cents(result.saved),
                remaining_cents=_cents(result.remaining),
                monthly_needed_cents=_cents(result.monthly_needed),
                progress_bps=result.progress_bps,
            )
        )
    return GoalsEvaluateResult(
        as_of=ctx.today, stale=any(row.stale for row in rows) or None, goals=rows
    )


# ── planning_profile ──────────────────────────────────────────────────────────


class AssumptionsRow(BaseModel):
    defaults: bool = Field(description="True: the app's defaults — nobody has set these. Say so.")
    set_on: dt.date
    expected_real_return_bps: int = Field(description="Expected yearly return after inflation.")
    inflation_bps: int
    withdrawal_low_bps: int
    withdrawal_high_bps: int
    pre65_healthcare_annual_cents: int | None = Field(
        default=None, description="A year of healthcare before Medicare. Null: not stated."
    )
    tax_deferred_withdrawal_tax_bps: int = Field(
        description="A flat effective rate on tax-deferred withdrawals — a simplification."
    )
    risk_tolerance: RiskTolerance
    target_us_equity_bps: int
    target_intl_equity_bps: int
    target_bonds_bps: int
    target_cash_bps: int
    target_other_bps: int


class PlanningProfileResult(ToolResult):
    birth_year: int | None = Field(default=None, description="The asker's. Null: not stated.")
    target_retirement_year: int | None = None
    assumptions: AssumptionsRow | None


def _bps(pct: Decimal) -> int:
    return int(pct.scaleb(2))


@REGISTRY.tool(
    "planning_profile",
    description=(
        "The asker's birth and target retirement years, and the planning assumptions in "
        "force: expected real return, inflation, a withdrawal band, healthcare before 65, a "
        "flat tax on tax-deferred withdrawals, risk tolerance and a target mix. Call it before "
        "any recommendation that depends on returns, inflation, tax or time, and name the "
        "assumptions you use — saying so when they are the defaults."
    ),
    label=lambda args: "Planning profile and assumptions",
)
def planning_profile(args: NoArgs, session: Session, ctx: ToolContext) -> PlanningProfileResult:
    profile = session.get(MemberProfile, ctx.user_id)
    current = session.execute(
        select(PlanningAssumptions)
        .order_by(PlanningAssumptions.effective_from.desc(), PlanningAssumptions.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return PlanningProfileResult(
        as_of=ctx.today,
        birth_year=profile.birth_year if profile else None,
        target_retirement_year=profile.target_retirement_year if profile else None,
        assumptions=(
            AssumptionsRow(
                defaults=current.is_default,
                set_on=current.effective_from.date(),
                expected_real_return_bps=current.expected_real_return_bps,
                inflation_bps=current.inflation_bps,
                withdrawal_low_bps=current.withdrawal_low_bps,
                withdrawal_high_bps=current.withdrawal_high_bps,
                pre65_healthcare_annual_cents=(
                    to_cents(current.pre65_healthcare_annual)
                    if current.pre65_healthcare_annual is not None
                    else None
                ),
                tax_deferred_withdrawal_tax_bps=current.tax_deferred_withdrawal_tax_bps,
                risk_tolerance=current.risk_tolerance,
                target_us_equity_bps=_bps(current.target_us_equity_pct),
                target_intl_equity_bps=_bps(current.target_intl_equity_pct),
                target_bonds_bps=_bps(current.target_bonds_pct),
                target_cash_bps=_bps(current.target_cash_pct),
                target_other_bps=_bps(current.target_other_pct),
            )
            if current
            else None
        ),
    )
