"""Retirement projections to PRODUCT's FIRE bar: a band across withdrawal rates and return
sequences, never a single number (ticket 117; docs/ADVISOR.md#projections).

**Everything is in today's dollars.** Returns are annual *real* returns from a committed table
(`returns.csv`, its source and licence in its header; nothing is fetched), so spending,
contributions and healthcare are held constant and inflation never appears.

**Annual steps, in `Decimal`, rounded once at output.** Each year starts with its cashflow — a
contribution while working, a withdrawal once retired — and then every bucket grows by its
year's return, weighted by the bucket's allocation. The months left in this year are ignored:
the first step is next year.

**Three buckets and an HSA**, from each account's `tax_treatment`: taxable, tax-deferred and
Roth; HSA money counts as Roth-like from 65 and is untouchable before; education (529) money and
property are left out. Accounts with no allocation entered are **left out and reported**, never
assumed to hold anything. Debts are not subtracted: their payments are already in spending.

**Withdrawals** go taxable → tax-deferred → Roth → HSA, a stated order. Tax-deferred money is
grossed up at the flat assumed rate and **not drawn before 59½** — modelled as from the year the
person turns 60, since only the birth year is known. 72(t), Roth ladders, required minimum
distributions, Social Security and pensions are not modelled, and every result says so.

**Sequence risk**: every start year in the table as a rolling window (wrapping past the last
year), plus a bootstrap of whole years drawn with replacement from a fixed seed, so a run is
reproducible run to run. A year is a success for a retirement year when spending is met every
year to the end age.

**The output is a band**: success for each withdrawal rate from the assumptions' low to high in
0.5-point steps, and success for a range of retirement years with the earliest reaching 90%.
`Projection` refuses to exist with fewer than two rates. PRODUCT rules out a calculator that
multiplies expenses by 25; this is how that survives.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AssetClass, TaxTreatment
from app.models.planning import MemberProfile, PlanningAssumptions
from app.services import allocations
from app.services.analysis import allocation as allocation_analysis
from app.services.analysis import cashflow
from app.services.analysis.numbers import ZERO, quantize_money

RETURNS_PATH = Path(__file__).with_name("returns.csv")
BOOTSTRAP_PATHS = 1000
SEED = 20260928
END_AGE = 95
#: Tax-deferred money is drawn from the year the person turns this old (59½, from a birth year).
DEFERRED_FROM_AGE = 60
HSA_FROM_AGE = 65
HEALTHCARE_UNTIL_AGE = 65
LATEST_RETIREMENT_AGE = 70
SUCCESS_TARGET_BPS = 9000
RATE_STEP_BPS = 50
#: A need this small is met: Decimal division can leave a residue of 1E-25.
_MET = Decimal("0.005")
_ONE = Decimal(1)
_BPS = Decimal(10000)

Bucket = Literal["taxable", "tax_deferred", "roth", "hsa"]
BUCKETS: tuple[Bucket, ...] = ("taxable", "tax_deferred", "roth", "hsa")
_BUCKET_OF: dict[TaxTreatment, Bucket] = {
    TaxTreatment.TAXABLE: "taxable",
    TaxTreatment.TAX_DEFERRED: "tax_deferred",
    TaxTreatment.ROTH: "roth",
    TaxTreatment.HSA: "hsa",
}

LIMITATIONS = [
    "Tax-deferred money is not drawn before 59½ (from the year you turn 60); 72(t) and "
    "Roth-ladder strategies are not modelled.",
    "Tax-deferred withdrawals are taxed at one flat effective rate; taxable withdrawals are "
    "untaxed, and required minimum distributions are not modelled.",
    "Social Security and pensions are not included.",
    "Spending and savings are held constant in today's dollars.",
    "Returns are past real returns; the future may differ.",
]


class ProjectionUnavailableError(ValueError):
    """Something a projection needs is missing: the returns table, a birth year, spending."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


# ── the returns table ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReturnsTable:
    years: list[int]
    rows: list[dict[AssetClass, Decimal]]
    source: str
    licence: str
    synthetic: bool


def load_returns(path: Path) -> ReturnsTable:
    """A returns table: `#` header lines naming `source:` and `licence:`, then a CSV of
    year and one real return per asset class, as decimal fractions."""
    meta: dict[str, str] = {}
    body: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            key, _, value = line[1:].partition(":")
            meta[key.strip().lower()] = value.strip()
        elif line.strip():
            body.append(line)
    if not meta.get("source") or not meta.get("licence"):
        raise ValueError(f"{path.name} must name its source and licence in its header.")
    years: list[int] = []
    rows: list[dict[AssetClass, Decimal]] = []
    for record in csv.DictReader(body):
        years.append(int(record["year"]))
        rows.append({cls: Decimal(record[cls.value]) for cls in AssetClass})
    if not rows:
        raise ValueError(f"{path.name} has no years.")
    return ReturnsTable(
        years=years,
        rows=rows,
        source=meta["source"],
        licence=meta["licence"],
        synthetic=meta.get("synthetic", "").lower() == "true",
    )


def default_returns() -> ReturnsTable:
    """The committed table. Missing or synthetic, there is no projection — never a made-up one."""
    if not RETURNS_PATH.exists():
        raise ProjectionUnavailableError(
            "no_returns_table", "The historical returns table has not been installed."
        )
    table = load_returns(RETURNS_PATH)
    if table.synthetic:
        raise ProjectionUnavailableError(
            "no_returns_table", "The installed returns table is synthetic, for tests only."
        )
    return table


# ── the plan ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Plan:
    """Everything a projection runs on, in today's dollars."""

    start_year: int
    birth_year: int
    balances: dict[Bucket, Decimal]
    #: Per bucket, the share of each asset class, as fractions summing to one.
    weights: dict[Bucket, dict[AssetClass, Decimal]]
    annual_contribution: Decimal
    annual_spending: Decimal
    healthcare_pre65: Decimal
    #: The flat effective rate on tax-deferred withdrawals, as a fraction.
    tax_deferred_rate: Decimal
    withdrawal_rates_bps: list[int]
    target_retirement_year: int | None = None
    end_age: int = END_AGE
    assumptions_id: int | None = None
    contribution_source: Literal["trailing_12_months", "override"] = "trailing_12_months"
    #: Value left out, with the reason: no allocation entered, or education money.
    excluded_unknown: Decimal = ZERO
    excluded_education: Decimal = ZERO
    notes: list[str] = field(default_factory=list)

    @property
    def horizon(self) -> int:
        """Years from `start_year` through the year the person turns `end_age`."""
        return max(1, self.birth_year + self.end_age - self.start_year + 1)


def rates_between(low_bps: int, high_bps: int) -> list[int]:
    return list(range(low_bps, high_bps + 1, RATE_STEP_BPS))


# ── one path ──────────────────────────────────────────────────────────────────


def _factors(plan: Plan, rows: list[dict[AssetClass, Decimal]]) -> list[list[Decimal]]:
    """Per bucket, per year: one plus the bucket's weighted real return."""
    out: list[list[Decimal]] = []
    for bucket in BUCKETS:
        weights = plan.weights.get(bucket, {})
        out.append([_ONE + sum((w * row[c] for c, w in weights.items()), ZERO) for row in rows])
    return out


def _accumulate(plan: Plan, factors: list[list[Decimal]]) -> list[list[Decimal]]:
    """The balances at the start of each year, before its cashflow, if still working."""
    balances = [plan.balances.get(bucket, ZERO) for bucket in BUCKETS]
    starts: list[list[Decimal]] = []
    for year in range(plan.horizon):
        starts.append(balances)
        balances = [
            (balances[k] + (plan.annual_contribution if k == 0 else ZERO)) * factors[k][year]
            for k in range(len(BUCKETS))
        ]
    starts.append(balances)
    return starts


def withdraw(balances: list[Decimal], need: Decimal, age: int, tax: Decimal) -> Decimal:
    """Take `need` from the buckets in order, in place. Returns what could not be met."""
    take = min(balances[0], need)
    balances[0] -= take
    need -= take
    if need > _MET and age >= DEFERRED_FROM_AGE and balances[1] > 0:
        gross = min(balances[1], need / (_ONE - tax))
        balances[1] -= gross
        need -= gross * (_ONE - tax)
    if need > _MET:
        take = min(balances[2], need)
        balances[2] -= take
        need -= take
    if need > _MET and age >= HSA_FROM_AGE:
        take = min(balances[3], need)
        balances[3] -= take
        need -= take
    return need if need > _MET else ZERO


@dataclass(frozen=True)
class PathOutcome:
    success: bool
    #: The first year spending was not met, or None.
    failed_year: int | None
    #: Balances by bucket at the start of each simulated year, after its cashflow.
    trail: list[list[Decimal]]


def run_path(
    plan: Plan,
    factors: list[list[Decimal]],
    starts: list[list[Decimal]],
    retire_index: int,
    need: Callable[[int], Decimal],
) -> PathOutcome:
    """Retire at `retire_index` years from the start and draw `need(age)` each year after."""
    index = min(max(retire_index, 0), plan.horizon)
    balances = list(starts[index])
    trail: list[list[Decimal]] = []
    for year in range(index, plan.horizon):
        age = plan.start_year + year - plan.birth_year
        short = withdraw(balances, need(age), age, plan.tax_deferred_rate)
        trail.append(list(balances))
        if short > 0:
            return PathOutcome(False, plan.start_year + year, trail)
        balances = [balances[k] * factors[k][year] for k in range(len(BUCKETS))]
    return PathOutcome(True, None, trail)


# ── many paths ────────────────────────────────────────────────────────────────


def historical_paths(table: ReturnsTable, length: int) -> list[list[dict[AssetClass, Decimal]]]:
    """Every start year as a rolling window, wrapping past the end of the table."""
    n = len(table.rows)
    return [[table.rows[(start + i) % n] for i in range(length)] for start in range(n)]


def bootstrap_paths(
    table: ReturnsTable, length: int, count: int, seed: int
) -> list[list[dict[AssetClass, Decimal]]]:
    """Whole years drawn with replacement, so each year's classes keep their correlation."""
    rng = random.Random(seed)
    n = len(table.rows)
    return [[table.rows[rng.randrange(n)] for _ in range(length)] for _ in range(count)]


@dataclass(frozen=True)
class Prepared:
    factors: list[list[Decimal]]
    starts: list[list[Decimal]]


def prepare(plan: Plan, rows: list[dict[AssetClass, Decimal]]) -> Prepared:
    """One sequence of years, ready to retire from in any year: each bucket's growth factors,
    and its balances at the start of every year while still working."""
    factors = _factors(plan, rows)
    return Prepared(factors, _accumulate(plan, factors))


def _prepare(plan: Plan, paths: list[list[dict[AssetClass, Decimal]]]) -> list[Prepared]:
    return [prepare(plan, rows) for rows in paths]


def _success_bps(
    plan: Plan, prepared: list[Prepared], retire_index: int, need: Callable[[int], Decimal]
) -> int:
    wins = sum(run_path(plan, p.factors, p.starts, retire_index, need).success for p in prepared)
    return wins * 10000 // len(prepared) if prepared else 0


# ── the result ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateResult:
    rate_bps: int
    historical_success_bps: int
    bootstrap_success_bps: int
    #: The rate applied to the median portfolio at retirement: a year's spending it supports.
    median_withdrawal: Decimal


@dataclass(frozen=True)
class YearResult:
    year: int
    age: int
    historical_success_bps: int
    bootstrap_success_bps: int


@dataclass(frozen=True)
class Projection:
    plan: Plan
    returns_source: str
    #: The retirement year the withdrawal-rate band is measured at.
    rates_at_year: int
    by_rate: list[RateResult]
    by_year: list[YearResult]
    earliest_year: int | None
    historical_paths: int
    bootstrap_paths: int
    seed: int
    limitations: list[str]

    def __post_init__(self) -> None:
        if len(self.by_rate) < 2:
            raise ValueError(
                "A projection is a band across withdrawal rates, never a single number."
            )
        if not self.by_year:
            raise ValueError("A projection needs a range of retirement years.")

    @property
    def assumptions_id(self) -> int | None:
        return self.plan.assumptions_id


def project(
    plan: Plan,
    table: ReturnsTable,
    *,
    bootstrap_count: int = BOOTSTRAP_PATHS,
    seed: int = SEED,
) -> Projection:
    """Success across withdrawal rates and retirement years, historical and bootstrapped."""
    if len(plan.withdrawal_rates_bps) < 2:
        raise ValueError("The withdrawal band needs a low and a high rate at least 0.5 apart.")
    length = plan.horizon
    history = _prepare(plan, historical_paths(table, length))
    boot = _prepare(plan, bootstrap_paths(table, length, bootstrap_count, seed))

    def spending(age: int) -> Decimal:
        extra = plan.healthcare_pre65 if age < HEALTHCARE_UNTIL_AGE else ZERO
        return plan.annual_spending + extra

    cache: dict[int, tuple[int, int]] = {}

    def at(year: int) -> tuple[int, int]:
        if year not in cache:
            index = year - plan.start_year
            cache[year] = (
                _success_bps(plan, history, index, spending),
                _success_bps(plan, boot, index, spending),
            )
        return cache[year]

    first = plan.start_year
    last = max(first, plan.birth_year + LATEST_RETIREMENT_AGE)
    earliest: int | None = None
    if min(at(last)) >= SUCCESS_TARGET_BPS:
        lo, hi = first, last  # success rises with the retirement year: the first to reach 90%
        while lo < hi:
            mid = (lo + hi) // 2
            if min(at(mid)) >= SUCCESS_TARGET_BPS:
                hi = mid
            else:
                lo = mid + 1
        earliest = lo
    around = earliest if earliest is not None else last
    years = {y for y in range(around - 2, around + 3) if first <= y <= last}
    if plan.target_retirement_year is not None:
        years.add(min(max(plan.target_retirement_year, first), last))
    by_year = [YearResult(y, y - plan.birth_year, *at(y)) for y in sorted(years)]

    rates_year = (
        plan.target_retirement_year or earliest or min(last, plan.birth_year + HEALTHCARE_UNTIL_AGE)
    )
    rates_year = min(max(rates_year, first), last)
    index = rates_year - first
    portfolios = sorted(sum(p.starts[index], ZERO) for p in history + boot)
    median = portfolios[len(portfolios) // 2]
    by_rate = []
    for rate in plan.withdrawal_rates_bps:
        fraction = Decimal(rate) / _BPS

        def fixed(p: Prepared, f: Decimal = fraction) -> Callable[[int], Decimal]:
            amount = sum(p.starts[index], ZERO) * f
            return lambda age: amount

        wins_h = sum(run_path(plan, p.factors, p.starts, index, fixed(p)).success for p in history)
        wins_b = sum(run_path(plan, p.factors, p.starts, index, fixed(p)).success for p in boot)
        by_rate.append(
            RateResult(
                rate_bps=rate,
                historical_success_bps=wins_h * 10000 // len(history),
                bootstrap_success_bps=wins_b * 10000 // len(boot) if boot else 0,
                median_withdrawal=quantize_money(median * fraction),
            )
        )

    limitations = list(LIMITATIONS) + list(plan.notes)
    if plan.excluded_unknown > 0:
        limitations.append(
            f"${plan.excluded_unknown:,.2f} in accounts with no allocation entered is left out."
        )
    if plan.excluded_education > 0:
        limitations.append(f"${plan.excluded_education:,.2f} of education (529) money is left out.")
    return Projection(
        plan=plan,
        returns_source=table.source,
        rates_at_year=rates_year,
        by_rate=by_rate,
        by_year=by_year,
        earliest_year=earliest,
        historical_paths=len(history),
        bootstrap_paths=len(boot),
        seed=seed,
        limitations=limitations,
    )


# ── from the database ─────────────────────────────────────────────────────────


def plan_for(
    session: Session,
    today: dt.date,
    user_id: int,
    viewer_id: int | None,
    *,
    annual_contribution: Decimal | None = None,
    annual_spending: Decimal | None = None,
    target_retirement_year: int | None = None,
) -> Plan:
    """The plan from what the app holds: the asker's profile, the assumptions in force, the
    asset mix in this scope and the last twelve complete months' cashflow."""
    profile = session.get(MemberProfile, user_id)
    if profile is None or profile.birth_year is None:
        raise ProjectionUnavailableError("no_birth_year", "A projection needs your birth year.")
    assumptions = session.execute(
        select(PlanningAssumptions)
        .order_by(PlanningAssumptions.effective_from.desc(), PlanningAssumptions.id.desc())
        .limit(1)
    ).scalar_one()

    mix = allocation_analysis.mix(session, today, viewer_id, user_id)
    totals: dict[Bucket, dict[AssetClass, Decimal]] = {b: {} for b in BUCKETS}
    unknown = education = ZERO
    for row in mix.accounts:
        if row.value <= 0:
            continue
        treatment = allocations.tax_treatment(session.get_one(Account, row.account_id))
        if treatment is TaxTreatment.EDUCATION:
            education += row.value
            continue
        bucket = _BUCKET_OF.get(treatment)
        if bucket is None:
            continue  # property and vehicles: not a portfolio
        if row.status == "unknown":
            unknown += row.value
            continue
        for cls, amount in row.parts.items():
            totals[bucket][cls] = totals[bucket].get(cls, ZERO) + amount
    balances = {b: sum(totals[b].values(), ZERO) for b in BUCKETS}
    weights = {
        b: {cls: amount / balances[b] for cls, amount in totals[b].items()}
        for b in BUCKETS
        if balances[b] > 0
    }
    notes: list[str] = []
    if "taxable" not in weights:
        # Savings land in taxable accounts. With none yet, they are invested like the rest.
        overall: dict[AssetClass, Decimal] = {}
        for b in BUCKETS:
            for cls, amount in totals[b].items():
                overall[cls] = overall.get(cls, ZERO) + amount
        whole = sum(overall.values(), ZERO)
        if whole > 0:
            weights["taxable"] = {cls: amount / whole for cls, amount in overall.items()}
            notes.append("New savings are invested like the rest of the portfolio.")

    flows = cashflow.monthly(session, today, 12)
    months = len(flows.months)
    if annual_spending is None:
        if months == 0:
            raise ProjectionUnavailableError(
                "no_spending_history", "A projection needs a year of spending, or a figure."
            )
        annual_spending = quantize_money(flows.spend * 12 / months)
    source: Literal["trailing_12_months", "override"] = "override"
    if annual_contribution is None:
        source = "trailing_12_months"
        saved = flows.net * 12 / months if months else ZERO
        annual_contribution = quantize_money(max(saved, ZERO))
        notes.append("Savings are added to taxable accounts, as the last twelve months' were.")
    healthcare = assumptions.pre65_healthcare_annual
    if healthcare is None:
        notes.append("No healthcare cost before 65 is stated, so none is included.")
    return Plan(
        start_year=today.year + 1,
        birth_year=profile.birth_year,
        balances=balances,
        weights=weights,
        annual_contribution=annual_contribution,
        annual_spending=annual_spending,
        healthcare_pre65=healthcare or ZERO,
        tax_deferred_rate=Decimal(assumptions.tax_deferred_withdrawal_tax_bps) / _BPS,
        withdrawal_rates_bps=rates_between(
            assumptions.withdrawal_low_bps, assumptions.withdrawal_high_bps
        ),
        target_retirement_year=target_retirement_year or profile.target_retirement_year,
        assumptions_id=assumptions.id,
        contribution_source=source,
        excluded_unknown=unknown,
        excluded_education=education,
        notes=notes,
    )
