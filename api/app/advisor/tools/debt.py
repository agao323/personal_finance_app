"""Debt tools: what each loan and card costs to carry (112), and what paying it down buys (115).

`debt_terms` lists every open liability with its balance and, where recorded, its terms: the
APR (to three decimals), the rate that applies today (a promotional one through its end date),
the minimum payment, the credit limit and utilisation, the term and maturity. A liability with
no terms says so, so the model can name the gap instead of guessing a rate.

`debt_compare_strategies` and `debt_prepay_vs_invest` are computed comparisons, both sides and
their assumptions returned, so the model explains a result instead of reaching for a rule of
thumb. They schedule **whole balances** — a lender amortises the whole loan — over the debts the
view includes, and report a debt with no terms, or no payment to schedule, as a limitation
rather than assuming a rate.

**Balances follow the view** — `mine` is the asker's share, `household` every stake — through
the net worth service, which rounds once, per account. **Utilisation uses the whole balance**:
it describes the account against its limit, not anyone's share of it.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.tools import REGISTRY, ToolArgs, ToolContext, ToolInputError, ToolResult
from app.models.account import Account
from app.models.enums import AccountKind, AccountSubtype
from app.schemas.common import ViewScope, from_cents, to_cents
from app.services import liability_terms as terms_service
from app.services import net_worth as net_worth_service
from app.services.analysis import debt as debt_analysis
from app.services.analysis.numbers import ratio_bps


class DebtTermsArgs(ToolArgs):
    view: ViewScope | None = Field(
        default=None,
        description="mine: your ownership share of each balance. household: every stake. "
        "Defaults to the conversation's view.",
    )


class DebtRow(BaseModel):
    account_id: int
    name_text: str
    subtype: AccountSubtype
    balance_cents: int = Field(description="The whole balance owed, before ownership.")
    share_cents: int = Field(description="The balance in this view: your share, or every stake.")
    balance_as_of: dt.date
    balance_stale: bool
    terms_recorded: bool
    apr_pct_thousandths: int | None = None
    today_apr_pct_thousandths: int | None = Field(
        default=None, description="The rate that applies today: a promotion through its end."
    )
    promo_apr_pct_thousandths: int | None = None
    promo_ends_on: dt.date | None = None
    minimum_payment_cents: int | None = None
    credit_limit_cents: int | None = None
    utilisation_bps: int | None = Field(
        default=None, description="The whole balance as a share of the credit limit."
    )
    term_months: int | None = None
    maturity_on: dt.date | None = None
    terms_as_of: dt.date | None = None
    terms_stale: bool | None = Field(
        default=None, description="The terms were last checked more than 365 days ago."
    )


class DebtTermsResult(ToolResult):
    debts: list[DebtRow]
    without_terms_count: int


@REGISTRY.tool(
    "debt_terms",
    description=(
        "Every open loan and card: its balance, and where recorded its APR, the rate that "
        "applies today, minimum payment, credit limit and utilisation, term and maturity. "
        "Call it for questions about interest, paying debt down, or credit utilisation. A "
        "debt with terms_recorded false has no rate on file: say so rather than assume one."
    ),
    label=lambda args: f"Debts and their terms{f', {args.view}' if args.view else ''}",
)
def debt_terms(args: DebtTermsArgs, session: Session, ctx: ToolContext) -> DebtTermsResult:
    viewer = ctx.viewer_id(args.view)
    worth = net_worth_service.net_worth(session, ctx.today, viewer)
    rows: list[DebtRow] = []
    for contribution in worth.contributions:
        if contribution.kind is not AccountKind.LIABILITY:
            continue
        account = session.get_one(Account, contribution.account_id)
        terms = terms_service.get(session, account.id)
        row = DebtRow(
            account_id=account.id,
            name_text=account.name,
            subtype=account.subtype,
            balance_cents=to_cents(contribution.raw_balance),
            share_cents=to_cents(contribution.adjusted_balance),
            balance_as_of=contribution.balance_as_of,
            balance_stale=contribution.is_stale,
            terms_recorded=terms is not None,
        )
        if terms is not None:
            row.apr_pct_thousandths = int(terms.apr.scaleb(3))
            row.today_apr_pct_thousandths = int(
                terms_service.effective_apr(terms, ctx.today).scaleb(3)
            )
            if terms.promo_apr is not None:
                row.promo_apr_pct_thousandths = int(terms.promo_apr.scaleb(3))
                row.promo_ends_on = terms.promo_ends_on
            if terms.minimum_payment is not None:
                row.minimum_payment_cents = to_cents(terms.minimum_payment)
            if terms.credit_limit is not None:
                row.credit_limit_cents = to_cents(terms.credit_limit)
                row.utilisation_bps = ratio_bps(contribution.raw_balance, terms.credit_limit)
            row.term_months = terms.term_months
            row.maturity_on = terms.maturity_on
            row.terms_as_of = terms.as_of
            row.terms_stale = terms_service.is_stale(terms, ctx.today)
        rows.append(row)
    return DebtTermsResult(
        as_of=ctx.today,
        view=args.view or ctx.view,
        stale=any(r.balance_stale or r.terms_stale for r in rows) or None,
        debts=rows,
        without_terms_count=sum(1 for r in rows if not r.terms_recorded),
    )


# ── avalanche and snowball (ticket 115) ───────────────────────────────────────

#: $100,000 a month: past any household's extra payment, short of an overflow.
MAX_EXTRA_CENTS = 10_000_000


def _tenths(months: int | None) -> int | None:
    return None if months is None else months * 10


class LimitationRow(BaseModel):
    account_id: int
    name_text: str
    reason: Literal["no_terms", "no_payment"] = Field(
        description="no_terms: no APR on file. no_payment: no minimum payment or maturity date."
    )


def _limitations(items: list[debt_analysis.Limitation]) -> list[LimitationRow]:
    return [
        LimitationRow(account_id=i.account_id, name_text=i.name, reason=i.reason) for i in items
    ]


class CompareArgs(ToolArgs):
    extra_monthly_cents: int = Field(
        ge=0,
        le=MAX_EXTRA_CENTS,
        description="Paid each month on top of every minimum. 0 compares the minimums alone.",
    )
    view: ViewScope | None = Field(
        default=None,
        description="Which debts: mine, those you hold a stake in; household, all of them. "
        "Defaults to the conversation's view.",
    )


class PayoffRow(BaseModel):
    account_id: int
    name_text: str
    paid_off_in_months_tenths: int | None = Field(
        description="Months from now until it reaches zero. Null: not within 50 years."
    )
    interest_cents: int


class PlanRow(BaseModel):
    strategy: Literal["avalanche", "snowball"]
    payoffs: list[PayoffRow] = Field(description="In the order the extra goes to them.")
    debt_free_in_months_tenths: int | None = Field(
        description="Months until every debt here is paid off. Null: not within 50 years."
    )
    total_interest_cents: int


class CompareResult(ToolResult):
    avalanche: PlanRow = Field(description="Highest APR first.")
    snowball: PlanRow = Field(description="Smallest balance first.")
    interest_difference_cents: int = Field(
        description="Snowball's total interest less avalanche's: what smallest-first costs."
    )
    months_difference_months_tenths: int | None = Field(
        description="Snowball's months to debt-free less avalanche's."
    )
    minimum_payments_cents: int
    extra_monthly_cents: int
    basis: Literal["whole_balances"] = Field(
        default="whole_balances",
        description="Whole balances, as the lender amortises them, not ownership shares.",
    )
    limitations: list[LimitationRow] = Field(
        description="Debts left out. Name each; never assume a rate for one."
    )


def _plan(plan: debt_analysis.Plan) -> PlanRow:
    return PlanRow(
        strategy=plan.strategy,
        payoffs=[
            PayoffRow(
                account_id=p.account_id,
                name_text=p.name,
                paid_off_in_months_tenths=_tenths(p.month),
                interest_cents=to_cents(p.interest),
            )
            for p in plan.payoffs
        ],
        debt_free_in_months_tenths=_tenths(plan.months_to_debt_free),
        total_interest_cents=to_cents(plan.total_interest),
    )


@REGISTRY.tool(
    "debt_compare_strategies",
    description=(
        "Avalanche (highest APR first) against snowball (smallest balance first) for paying "
        "off every debt with terms: payoff order, months to debt-free and total interest for "
        "each, and the difference. Every minimum is paid monthly, the extra goes to the first "
        "debt in order, and each freed minimum rolls onto the next. Call it for 'which debt "
        "first?'; name any limitations."
    ),
    label=lambda args: f"Avalanche and snowball, {args.extra_monthly_cents / 100:,.2f} extra",
)
def debt_compare_strategies(args: CompareArgs, session: Session, ctx: ToolContext) -> CompareResult:
    result = debt_analysis.strategies(
        session, ctx.today, ctx.viewer_id(args.view), from_cents(args.extra_monthly_cents)
    )
    return CompareResult(
        as_of=ctx.today,
        view=args.view or ctx.view,
        avalanche=_plan(result.avalanche),
        snowball=_plan(result.snowball),
        interest_difference_cents=to_cents(result.interest_difference),
        months_difference_months_tenths=_tenths(result.months_difference),
        minimum_payments_cents=to_cents(result.minimum_payments),
        extra_monthly_cents=args.extra_monthly_cents,
        limitations=_limitations(result.limitations),
    )


# ── prepaying against investing (ticket 115) ──────────────────────────────────


class PrepayArgs(ToolArgs):
    account_id: int = Field(ge=1, le=2_147_483_647, description="From debt_terms.")
    extra_monthly_cents: int = Field(
        ge=100, le=MAX_EXTRA_CENTS, description="The extra each month, prepaid or invested."
    )
    horizon_years: int = Field(
        ge=1, le=debt_analysis.MAX_HORIZON_YEARS, description="How far ahead to compare."
    )
    view: ViewScope | None = Field(
        default=None, description="mine or household. Defaults to the conversation's view."
    )


class PathRow(BaseModel):
    debt_free_in_months_tenths: int | None = Field(
        description="Months until the debt is paid off. Null: not within the horizon."
    )
    interest_paid_cents: int = Field(description="Within the horizon.")
    debt_left_cents: int = Field(description="Still owed at the horizon.")
    invested_cents: int = Field(description="Put in over the horizon, before growth.")
    investments_cents: int = Field(description="What was invested, grown, at the horizon.")
    net_cents: int = Field(description="Investments less the debt left.")


class AssumptionsUsed(BaseModel):
    real_return_bps: int
    inflation_bps: int
    nominal_return_bps: int = Field(
        description="Real return and inflation combined, because the loan's rate is nominal."
    )
    defaults: bool = Field(description="True: the planning defaults, not the household's own.")


class PrepayResult(ToolResult):
    account_id: int
    name_text: str
    limitation: Literal["no_terms", "no_payment"] | None = Field(
        default=None, description="Set when nothing could be computed: name it, never guess."
    )
    balance_cents: int | None = None
    apr_pct_thousandths: int | None = None
    payment_cents: int | None = None
    payment_source: Literal["minimum", "level_to_maturity"] | None = None
    extra_monthly_cents: int
    horizon_years: int
    prepay: PathRow | None = Field(
        default=None, description="The extra to the debt; everything invested once it is gone."
    )
    invest: PathRow | None = Field(
        default=None, description="The extra invested from the start; the payment too, later."
    )
    difference_cents: int | None = Field(
        default=None, description="Investing's net less prepaying's. Positive: investing ahead."
    )
    interest_saved_cents: int | None = Field(
        default=None, description="Interest prepaying avoids within the horizon."
    )
    assumptions: AssumptionsUsed | None = None
    exclusions: list[str] = Field(default_factory=list, description="Say these with the result.")


def _path(path: debt_analysis.Path) -> PathRow:
    return PathRow(
        debt_free_in_months_tenths=_tenths(path.debt_free_month),
        interest_paid_cents=to_cents(path.interest_paid),
        debt_left_cents=to_cents(path.debt_left),
        invested_cents=to_cents(path.invested),
        investments_cents=to_cents(path.investments),
        net_cents=to_cents(path.net),
    )


@REGISTRY.tool(
    "debt_prepay_vs_invest",
    description=(
        "For one debt: the same money each month spent two ways over a horizon — the extra "
        "prepaid on the debt, or invested at the planning assumptions' return — with interest "
        "saved, both end values and the difference. Call it for 'pay down the loan or "
        "invest?'. Quote the assumptions and the exclusions with the result, and present both "
        "sides as options."
    ),
    label=lambda args: f"Prepay or invest, {args.horizon_years} years",
)
def debt_prepay_vs_invest(args: PrepayArgs, session: Session, ctx: ToolContext) -> PrepayResult:
    outcome = debt_analysis.prepay_vs_invest(
        session,
        ctx.today,
        ctx.viewer_id(args.view),
        args.account_id,
        from_cents(args.extra_monthly_cents),
        args.horizon_years,
    )
    common = {
        "as_of": ctx.today,
        "view": args.view or ctx.view,
        "account_id": args.account_id,
        "extra_monthly_cents": args.extra_monthly_cents,
        "horizon_years": args.horizon_years,
    }
    if outcome is None:
        raise ToolInputError(
            f"No debt with id {args.account_id} is owed in this view. Use debt_terms for ids."
        )
    if isinstance(outcome, debt_analysis.Limitation):
        return PrepayResult(name_text=outcome.name, limitation=outcome.reason, **common)
    debt = outcome.debt
    return PrepayResult(
        name_text=debt.name,
        balance_cents=to_cents(debt.balance),
        apr_pct_thousandths=int(debt.apr.scaleb(3)),
        payment_cents=to_cents(debt.payment),
        payment_source=debt.payment_source,
        prepay=_path(outcome.prepay),
        invest=_path(outcome.invest),
        difference_cents=to_cents(outcome.difference),
        interest_saved_cents=to_cents(outcome.interest_saved),
        assumptions=AssumptionsUsed(
            real_return_bps=outcome.assumptions.real_return_bps,
            inflation_bps=outcome.assumptions.inflation_bps,
            nominal_return_bps=outcome.assumptions.nominal_return_bps,
            defaults=outcome.assumptions.defaults,
        ),
        exclusions=outcome.exclusions,
        **common,
    )
