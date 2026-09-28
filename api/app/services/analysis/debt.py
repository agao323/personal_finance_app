"""Debt: amortisation, avalanche against snowball, prepaying against investing, utilisation.

**Interest is rounded to cents every month, half-up**, because that is what a lender's
statement does. It is the one place a derived figure is rounded more than once (see
`numbers.py`): a schedule that rounded once at the end would drift from the statement by a
few cents a year and be wrong in the way that matters. Payments are whole cents already, so
every balance in a schedule is exact to the cent. Investment growth in `prepay_vs_invest` is
not a statement and rounds once, at the edge, like every other derived figure.

**Balances are whole**, not ownership shares: a lender amortises the whole loan whoever owns
it, exactly as utilisation compares the whole balance with the limit. Which debts are included
follows the view — `mine` is the debts the viewer holds a stake in.

A debt with no terms is **never assumed at 0%**. It is left out and reported as a limitation,
as is one with an APR but no payment to schedule — no minimum payment and no maturity date to
derive a level payment from.

Month `n` of a schedule is the payment `n` months after `today`. A promotional rate applies to
every month whose payment date falls on or before the promotion's end.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind, AccountSubtype
from app.models.liability_terms import LiabilityTerms
from app.models.planning import PlanningAssumptions
from app.services import net_worth as net_worth_service
from app.services.analysis.numbers import ZERO, quantize_money, ratio_bps
from app.services.perks import add_months

#: A schedule that has not ended in fifty years never will at these payments.
MAX_MONTHS = 600
MAX_HORIZON_YEARS = 40
_MONTHS_A_YEAR = Decimal(12)
_HUNDRED = Decimal(100)
_ONE = Decimal(1)

Strategy = Literal["avalanche", "snowball"]


def monthly_interest(balance: Decimal, apr: Decimal) -> Decimal:
    """One month's interest on `balance` at `apr` percent, to the cent, half-up."""
    return (balance * apr / _HUNDRED / _MONTHS_A_YEAR).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


@dataclass(frozen=True)
class Debt:
    account_id: int
    name: str
    subtype: AccountSubtype
    balance: Decimal
    apr: Decimal
    payment: Decimal
    #: Where the payment came from: the recorded minimum, or a level payment to maturity.
    payment_source: Literal["minimum", "level_to_maturity"]
    promo_apr: Decimal | None = None
    promo_ends_on: dt.date | None = None

    def rate(self, paid_on: dt.date) -> Decimal:
        if (
            self.promo_apr is not None
            and self.promo_ends_on is not None
            and paid_on <= self.promo_ends_on
        ):
            return self.promo_apr
        return self.apr


@dataclass(frozen=True)
class Limitation:
    account_id: int
    name: str
    reason: Literal["no_terms", "no_payment"]


@dataclass(frozen=True)
class Month:
    number: int
    paid_on: dt.date
    interest: Decimal
    payment: Decimal
    balance: Decimal


@dataclass(frozen=True)
class Schedule:
    months: list[Month]
    total_interest: Decimal
    #: The month the balance reached zero, or None when it had not by the end.
    paid_off_month: int | None


def amortise(
    debt: Debt, today: dt.date, payment: Decimal, max_months: int = MAX_MONTHS
) -> Schedule:
    """A month-by-month schedule: interest first, then the payment, capped at what is owed."""
    balance = debt.balance
    months: list[Month] = []
    total = ZERO
    for number in range(1, max_months + 1):
        if balance <= 0:
            break
        paid_on = add_months(today, number)
        interest = monthly_interest(balance, debt.rate(paid_on))
        owed = balance + interest
        paid = min(owed, payment)
        balance = owed - paid
        total += interest
        months.append(Month(number, paid_on, interest, paid, balance))
    return Schedule(months, total, len(months) if balance <= 0 else None)


def level_payment(balance: Decimal, apr: Decimal, months: int) -> Decimal:
    """The payment that clears `balance` in `months` at `apr`, rounded up to the cent.

    Rounded up, not half-up, so the last payment is never larger than the rest.
    """
    if months <= 0:
        return balance
    rate = apr / _HUNDRED / _MONTHS_A_YEAR
    if rate == 0:
        exact = balance / months
    else:
        exact = balance * rate / (_ONE - (_ONE + rate) ** -months)
    return exact.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _months_between(start: dt.date, end: dt.date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def debts(
    session: Session, today: dt.date, viewer_id: int | None
) -> tuple[list[Debt], list[Limitation]]:
    """Every open debt owed in the view: those that can be scheduled, and the rest."""
    worth = net_worth_service.net_worth(session, today, viewer_id)
    ready: list[Debt] = []
    limited: list[Limitation] = []
    for contribution in worth.contributions:
        if contribution.kind is not AccountKind.LIABILITY or contribution.raw_balance <= 0:
            continue
        account = session.get_one(Account, contribution.account_id)
        terms = session.get(LiabilityTerms, account.id)
        if terms is None:
            limited.append(Limitation(account.id, account.name, "no_terms"))
            continue
        source: Literal["minimum", "level_to_maturity"]
        if terms.minimum_payment is not None and terms.minimum_payment > 0:
            payment, source = terms.minimum_payment, "minimum"
        elif terms.maturity_on is not None and terms.maturity_on > today:
            remaining = max(1, _months_between(today, terms.maturity_on))
            payment = level_payment(contribution.raw_balance, terms.apr, remaining)
            source = "level_to_maturity"
        else:
            limited.append(Limitation(account.id, account.name, "no_payment"))
            continue
        ready.append(
            Debt(
                account_id=account.id,
                name=account.name,
                subtype=account.subtype,
                balance=contribution.raw_balance,
                apr=terms.apr,
                payment=payment,
                payment_source=source,
                promo_apr=terms.promo_apr,
                promo_ends_on=terms.promo_ends_on,
            )
        )
    return ready, limited


# ── avalanche and snowball ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Payoff:
    account_id: int
    name: str
    #: The month this debt reached zero, or None when it had not within MAX_MONTHS.
    month: int | None
    interest: Decimal


@dataclass(frozen=True)
class Plan:
    strategy: Strategy
    #: Debts in the order the extra goes to them.
    order: list[int]
    payoffs: list[Payoff]
    months_to_debt_free: int | None
    total_interest: Decimal


def order_for(strategy: Strategy, owed: list[Debt]) -> list[Debt]:
    """Avalanche: highest APR first, then the smaller balance. Snowball: smallest balance
    first, then the higher APR. The ongoing APR, not a promotion that will end."""
    if strategy == "avalanche":
        return sorted(owed, key=lambda d: (-d.apr, d.balance, d.account_id))
    return sorted(owed, key=lambda d: (d.balance, -d.apr, d.account_id))


def plan(strategy: Strategy, owed: list[Debt], extra: Decimal, today: dt.date) -> Plan:
    """Every minimum paid each month; the extra, and each minimum freed by a payoff, goes to
    the first debt in the strategy's order that is still owed."""
    ordered = order_for(strategy, owed)
    budget = sum((d.payment for d in owed), ZERO) + extra
    balance = {d.account_id: d.balance for d in owed}
    interest = {d.account_id: ZERO for d in owed}
    paid_off: dict[int, int] = {}
    for number in range(1, MAX_MONTHS + 1):
        live = [d for d in ordered if balance[d.account_id] > 0]
        if not live:
            break
        paid_on = add_months(today, number)
        for debt in live:
            charge = monthly_interest(balance[debt.account_id], debt.rate(paid_on))
            balance[debt.account_id] += charge
            interest[debt.account_id] += charge
        available = budget
        for debt in live:
            paid = min(balance[debt.account_id], debt.payment, available)
            balance[debt.account_id] -= paid
            available -= paid
        for debt in live:
            if available <= 0:
                break
            paid = min(balance[debt.account_id], available)
            balance[debt.account_id] -= paid
            available -= paid
        for debt in live:
            if balance[debt.account_id] <= 0:
                paid_off[debt.account_id] = number
    payoffs = [
        Payoff(d.account_id, d.name, paid_off.get(d.account_id), interest[d.account_id])
        for d in ordered
    ]
    done = len(paid_off) == len(owed)
    return Plan(
        strategy=strategy,
        order=[d.account_id for d in ordered],
        payoffs=payoffs,
        months_to_debt_free=max(paid_off.values(), default=0) if done else None,
        total_interest=sum(interest.values(), ZERO),
    )


@dataclass(frozen=True)
class Comparison:
    avalanche: Plan
    snowball: Plan
    #: Snowball's interest minus avalanche's: what the smallest-first order costs.
    interest_difference: Decimal
    #: Snowball's months minus avalanche's, when both finish.
    months_difference: int | None
    minimum_payments: Decimal
    extra: Decimal
    limitations: list[Limitation]


def strategies(
    session: Session, today: dt.date, viewer_id: int | None, extra_monthly: Decimal
) -> Comparison:
    owed, limited = debts(session, today, viewer_id)
    avalanche = plan("avalanche", owed, extra_monthly, today)
    snowball = plan("snowball", owed, extra_monthly, today)
    months = (
        snowball.months_to_debt_free - avalanche.months_to_debt_free
        if snowball.months_to_debt_free is not None and avalanche.months_to_debt_free is not None
        else None
    )
    return Comparison(
        avalanche=avalanche,
        snowball=snowball,
        interest_difference=snowball.total_interest - avalanche.total_interest,
        months_difference=months,
        minimum_payments=sum((d.payment for d in owed), ZERO),
        extra=extra_monthly,
        limitations=limited,
    )


# ── prepaying against investing ───────────────────────────────────────────────


@dataclass(frozen=True)
class Assumptions:
    id: int | None
    defaults: bool
    real_return_bps: int
    inflation_bps: int
    #: (1 + real)(1 + inflation) - 1, because the loan's rate is nominal.
    nominal_return_bps: int


def assumptions(session: Session) -> Assumptions:
    row = session.execute(
        select(PlanningAssumptions)
        .order_by(PlanningAssumptions.effective_from.desc(), PlanningAssumptions.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    real, inflation = (row.expected_real_return_bps, row.inflation_bps) if row else (500, 250)
    nominal = (_ONE + Decimal(real).scaleb(-4)) * (_ONE + Decimal(inflation).scaleb(-4)) - _ONE
    return Assumptions(
        id=row.id if row else None,
        defaults=row.is_default if row else True,
        real_return_bps=real,
        inflation_bps=inflation,
        nominal_return_bps=int(nominal.scaleb(4).quantize(_ONE, rounding=ROUND_HALF_UP)),
    )


@dataclass(frozen=True)
class Path:
    """One way of spending the same money each month over the horizon."""

    debt_free_month: int | None
    interest_paid: Decimal
    debt_left: Decimal
    invested: Decimal
    #: What was invested, grown; rounded once, here.
    investments: Decimal
    #: Investments less the debt left.
    net: Decimal


@dataclass(frozen=True)
class PrepayOrInvest:
    debt: Debt
    horizon_months: int
    extra: Decimal
    prepay: Path
    invest: Path
    #: Investing's net less prepaying's: positive when investing comes out ahead.
    difference: Decimal
    #: Interest prepaying avoids within the horizon.
    interest_saved: Decimal
    assumptions: Assumptions
    exclusions: list[str] = field(default_factory=list)


EXCLUSIONS = [
    "Mortgage-interest deductibility is not modelled.",
    "Taxes on investment returns are not modelled.",
    "Returns are steady at the assumed rate; real returns vary year to year.",
]


def _path(
    debt: Debt,
    payment: Decimal,
    budget: Decimal,
    months: int,
    today: dt.date,
    monthly_return: Decimal,
) -> Path:
    """Pay `payment` on the debt each month and invest what is left of `budget`."""
    schedule = amortise(debt, today, payment, max_months=months)
    by_month = {m.number: m for m in schedule.months}
    value = Decimal(0)
    invested = ZERO
    for number in range(1, months + 1):
        on_debt = by_month[number].payment if number in by_month else ZERO
        contribution = budget - on_debt
        value = value * (_ONE + monthly_return) + contribution
        invested += contribution
    left = schedule.months[-1].balance if schedule.months else debt.balance
    grown = quantize_money(value)
    return Path(
        debt_free_month=schedule.paid_off_month,
        interest_paid=schedule.total_interest,
        debt_left=left,
        invested=invested,
        investments=grown,
        net=grown - left,
    )


def prepay_vs_invest(
    session: Session,
    today: dt.date,
    viewer_id: int | None,
    account_id: int,
    extra_monthly: Decimal,
    horizon_years: int,
) -> PrepayOrInvest | Limitation | None:
    """The same money each month — the payment plus `extra_monthly` — spent two ways.

    **Prepay:** the extra goes to the debt; once it is paid off, the whole amount is invested.
    **Invest:** the debt gets its payment; the extra is invested from the start, and the
    payment too once the debt is paid off. Both are measured at the horizon: investments
    less the debt left. `None` when the account is not an owed debt in this view; a
    `Limitation` when its terms or payment are missing.
    """
    if not 1 <= horizon_years <= MAX_HORIZON_YEARS:
        raise ValueError(f"The horizon is 1 to {MAX_HORIZON_YEARS} years.")
    owed, limited = debts(session, today, viewer_id)
    debt = next((d for d in owed if d.account_id == account_id), None)
    if debt is None:
        return next((item for item in limited if item.account_id == account_id), None)
    found = assumptions(session)
    yearly = Decimal(found.nominal_return_bps).scaleb(-4)
    monthly_return = (_ONE + yearly) ** (_ONE / _MONTHS_A_YEAR) - _ONE
    months = horizon_years * 12
    budget = debt.payment + extra_monthly
    prepay = _path(debt, budget, budget, months, today, monthly_return)
    invest = _path(debt, debt.payment, budget, months, today, monthly_return)
    return PrepayOrInvest(
        debt=debt,
        horizon_months=months,
        extra=extra_monthly,
        prepay=prepay,
        invest=invest,
        difference=invest.net - prepay.net,
        interest_saved=invest.interest_paid - prepay.interest_paid,
        assumptions=found,
        exclusions=list(EXCLUSIONS),
    )


# ── utilisation ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardUtilisation:
    account_id: int
    name: str
    balance: Decimal
    limit: Decimal
    bps: int


@dataclass(frozen=True)
class Utilisation:
    cards: list[CardUtilisation]
    #: Every card's balance over every card's limit; None with no limits recorded.
    overall_bps: int | None
    balance: Decimal
    limit: Decimal
    #: Cards in the view with no limit recorded, and so not counted.
    without_limit: list[int]


def utilisation(session: Session, today: dt.date, viewer_id: int | None) -> Utilisation:
    """Per card and overall, whole balance over limit — the account against its limit."""
    worth = net_worth_service.net_worth(session, today, viewer_id)
    cards: list[CardUtilisation] = []
    without: list[int] = []
    for contribution in worth.contributions:
        account = session.get_one(Account, contribution.account_id)
        if account.subtype is not AccountSubtype.CREDIT_CARD:
            continue
        terms = session.get(LiabilityTerms, account.id)
        if terms is None or terms.credit_limit is None:
            without.append(account.id)
            continue
        balance = max(contribution.raw_balance, ZERO)
        cards.append(
            CardUtilisation(
                account.id,
                account.name,
                balance,
                terms.credit_limit,
                ratio_bps(balance, terms.credit_limit) or 0,
            )
        )
    balance = sum((c.balance for c in cards), ZERO)
    limit = sum((c.limit for c in cards), ZERO)
    return Utilisation(cards, ratio_bps(balance, limit), balance, limit, without)
