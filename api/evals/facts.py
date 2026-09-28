"""Every expected figure in the golden set, computed — never typed in.

A fact is a function of `(session, today)`. Each runs the **same tool function the model
calls**, with the same arguments a correct answer needs, and picks one field of the typed
result. So an expected answer is, by construction, a value the model could have been shown:
it can disagree with a tool only if the model asked the wrong question.

`python -m evals.fixtures` (`make eval-fixtures`) computes them all into `expected.json`; a CI
test recomputes them and fails on drift, so a service change that moves an answer shows up as
a diff someone reads.

Units: `cents`, `bps`, `months_tenths` and `count` are integers; `text` must appear in the
answer as written (case-insensitively); `date` is ISO.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all
from app.models.transaction import Category
from app.models.user import User
from app.schemas.common import ViewScope
from evals import overlay, synthetic_returns

Unit = str


@dataclass(frozen=True)
class Fact:
    unit: Unit
    compute: Callable[[Session, dt.date], Any]
    description: str


def _owner(session: Session) -> int:
    return int(session.execute(select(User.id).order_by(User.id)).scalars().first() or 0)


def _category(session: Session, name: str) -> int:
    return int(session.execute(select(Category.id).where(Category.name == name)).scalar_one())


def run_tool(
    session: Session,
    today: dt.date,
    name: str,
    args: dict[str, Any],
    view: ViewScope = ViewScope.HOUSEHOLD,
) -> Any:
    """A tool's typed result, exactly as the loop would compute it for the model."""
    spec = load_all().spec(name)

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield session

    ctx = ToolContext(today=today, user_id=_owner(session), view=view, sessions=same_session)
    return spec.fn(spec.args_model.model_validate(args), session, ctx)


def _networth(field: str, view: ViewScope) -> Callable[[Session, dt.date], Any]:
    return lambda s, t: getattr(run_tool(s, t, "networth_get", {"view": view}, view), field)


def _runway(view: ViewScope) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(s, t, "runway_get", {"view": view}, view)
        return next(w.runway_months_tenths for w in result.windows if w.months == 6)

    return compute


def _liquid(view: ViewScope) -> Callable[[Session, dt.date], Any]:
    return lambda s, t: run_tool(s, t, "runway_get", {"view": view}, view).liquid_assets_cents


def _recurring(merchant: str, field: str) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(s, t, "spend_recurring", {"lookback_months": 12})
        row = next(r for r in result.charges if r.merchant_text.upper() == merchant)
        return getattr(row, field)

    return compute


def _urgent_perk(field: str) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(s, t, "cards_upcoming_perks", {"within_days": 30})
        return getattr(
            next(p for p in result.perks if p.perk_name_text == overlay.URGENT_PERK), field
        )

    return compute


def _trend_month(field: str) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(
            s, t, "spend_trend", {"category_id": _category(s, "Restaurants"), "months": 12}
        )
        return getattr(next(m for m in result.months if m.month == "2026-07"), field)

    return compute


def _dining_quarter(field: str) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(
            s,
            t,
            "spend_compare",
            {
                "period_a": {"preset": "this_quarter"},
                "period_b": {"preset": "last_quarter"},
                "category_id": _category(s, "Restaurants"),
            },
        )
        return getattr(result, field)

    return compute


def _cashflow(field: str) -> Callable[[Session, dt.date], Any]:
    return lambda s, t: getattr(run_tool(s, t, "cashflow_get", {"months": 1}).months[-1], field)


def _stale_days(s: Session, t: dt.date) -> int:
    result = run_tool(s, t, "data_health", {})
    row = next(a for a in result.accounts if a.name_text == overlay.STALE_ACCOUNT)
    return int((t - row.balance_as_of).days)


def _transfer_amount(s: Session, t: dt.date) -> int:
    result = run_tool(s, t, "data_health", {})
    return int(result.possible_unmarked_transfers[0].amount_cents)


def _top_july_restaurant(s: Session, t: dt.date) -> str:
    result = run_tool(
        s,
        t,
        "spend_top_merchants",
        {"period": {"preset": "last_month"}, "category_id": _category(s, "Restaurants")},
    )
    return str(result.merchants[0].merchant_text)


def _nw_change_ytd(s: Session, t: dt.date) -> int:
    result = run_tool(
        s, t, "networth_explain_change", {"view": "household", "from_date": dt.date(t.year, 1, 1)}
    )
    return int(result.change_cents)


def _lapsed_merchant(s: Session, t: dt.date) -> str:
    result = run_tool(s, t, "spend_recurring", {"lookback_months": 12})
    (row,) = [r for r in result.charges if r.status == "lapsed"]
    return str(row.merchant_text)


def _risen_merchant(s: Session, t: dt.date) -> str:
    """The planted subscription whose price rose — checked to be one the tool reports."""
    result = run_tool(s, t, "spend_recurring", {"lookback_months": 12})
    (row,) = [r for r in result.charges if r.merchant_text.upper() == overlay.STREAMLY]
    assert row.price_increase_cents, "the overlay's price rise is not detected"
    return str(row.merchant_text)


def _stale_account(s: Session, t: dt.date) -> str:
    result = run_tool(s, t, "data_health", {})
    (row,) = [a for a in result.accounts if a.balance_stale]
    return str(row.name_text)


def _urgent_perk_name(s: Session, t: dt.date) -> str:
    result = run_tool(s, t, "cards_upcoming_perks", {"within_days": 30})
    (row,) = [p for p in result.perks if p.urgent]
    return str(row.perk_name_text)


def _goal(name: str, field: str) -> Callable[[Session, dt.date], Any]:
    def compute(s: Session, t: dt.date) -> Any:
        result = run_tool(s, t, "goals_evaluate", {})
        return getattr(next(r for r in result.goals if r.goal.name_text == name), field)

    return compute


def _assumption(field: str) -> Callable[[Session, dt.date], Any]:
    return lambda s, t: getattr(run_tool(s, t, "planning_profile", {}).assumptions, field)


def _band_rate(rate_bps: int) -> Callable[[Session, dt.date], Any]:
    """Bootstrap success at one withdrawal rate, at the target year (ticket 118)."""

    def compute(s: Session, t: dt.date) -> Any:
        band = run_tool(s, t, "projection_retirement", {}).band
        return next(r for r in band.by_rate if r.rate_bps == rate_bps).bootstrap_success_bps

    return compute


def _earliest_year(s: Session, t: dt.date) -> Any:
    return run_tool(s, t, "projection_retirement", {}).band.earliest_year


def _what_if_year(change: str, value: int) -> Callable[[Session, dt.date], Any]:
    """The scenario's earliest 90% year after one change."""
    return lambda s, t: (
        run_tool(
            s, t, "projection_what_if", {"change": change, "value": value}
        ).scenario.earliest_year
    )


H, M = ViewScope.HOUSEHOLD, ViewScope.MINE

FACTS: dict[str, Fact] = {
    # net worth and balances
    "nw_household": Fact("cents", _networth("net_worth_cents", H), "Household net worth"),
    "nw_mine": Fact("cents", _networth("net_worth_cents", M), "Mine net worth"),
    "assets_household": Fact("cents", _networth("assets_cents", H), "Household assets"),
    "liabilities_household": Fact(
        "cents", _networth("liabilities_cents", H), "Household liabilities"
    ),
    "assets_mine": Fact("cents", _networth("assets_cents", M), "Mine assets"),
    "stale_count": Fact("count", _networth("stale_account_count", H), "Stale balances"),
    "nw_change_ytd": Fact("cents", _nw_change_ytd, "Household net worth change this year"),
    # runway
    "runway_household": Fact("months_tenths", _runway(H), "Household runway, 6-month burn"),
    "runway_mine": Fact("months_tenths", _runway(M), "Mine runway, 6-month burn"),
    "liquid_household": Fact("cents", _liquid(H), "Household liquid assets"),
    "liquid_mine": Fact("cents", _liquid(M), "Mine liquid assets"),
    # spending
    "dining_this_quarter": Fact("cents", _dining_quarter("total_a_cents"), "Dining, this quarter"),
    "dining_last_quarter": Fact(
        "cents", _dining_quarter("total_b_cents"), "Dining, last quarter like-for-like"
    ),
    "dining_quarter_change": Fact(
        "cents", _dining_quarter("total_change_cents"), "Dining change, quarter on quarter"
    ),
    "restaurants_july": Fact("cents", _trend_month("spend_cents"), "Restaurants in July"),
    "restaurants_usual": Fact(
        "cents", _trend_month("trailing_median_cents"), "Restaurants, usual month"
    ),
    "top_july_restaurant": Fact("text", _top_july_restaurant, "Top restaurant merchant, July"),
    "income_last_month": Fact("cents", _cashflow("income_cents"), "Income, July"),
    "spend_last_month": Fact("cents", _cashflow("spend_cents"), "Spending, July"),
    "net_last_month": Fact("cents", _cashflow("net_cents"), "Net cash flow, July"),
    # recurring
    "streamly_increase": Fact(
        "cents", _recurring(overlay.STREAMLY, "price_increase_cents"), "STREAMLY price rise"
    ),
    "streamly_price": Fact(
        "cents", _recurring(overlay.STREAMLY, "last_amount_cents"), "STREAMLY new price"
    ),
    "newsdaily_price": Fact(
        "cents", _recurring(overlay.NEWSDAILY, "typical_cents"), "Annual subscription price"
    ),
    "recurring_annual_total": Fact(
        "cents",
        lambda s, t: (
            run_tool(s, t, "spend_recurring", {"lookback_months": 12}).active_annual_total_cents
        ),
        "Active recurring charges per year",
    ),
    "lapsed_merchant": Fact("text", _lapsed_merchant, "The lapsed subscription"),
    "streamly_merchant": Fact("text", _risen_merchant, "The subscription that rose"),
    # data quality
    "stale_account": Fact("text", _stale_account, "The stale account"),
    "stale_days": Fact("count", _stale_days, "Days since the stale balance"),
    "transfer_amount": Fact("cents", _transfer_amount, "The unmarked transfer"),
    # cards
    "urgent_perk": Fact("text", _urgent_perk_name, "The urgent perk"),
    "urgent_perk_value": Fact("cents", _urgent_perk("value_cents"), "Urgent perk value"),
    "urgent_perk_days": Fact("count", _urgent_perk("days_remaining"), "Urgent perk days left"),
    # goals and assumptions (ticket 111)
    "dining_limit_mtd": Fact(
        "cents", _goal(overlay.DINING_GOAL, "month_to_date_cents"), "Dining this month vs limit"
    ),
    "fund_runway": Fact(
        "months_tenths",
        _goal(overlay.FUND_GOAL, "runway_months_tenths"),
        "Emergency fund: months covered",
    ),
    "house_saved": Fact("cents", _goal(overlay.HOUSE_GOAL, "saved_cents"), "House deposit saved"),
    "house_monthly_needed": Fact(
        "cents",
        _goal(overlay.HOUSE_GOAL, "monthly_needed_cents"),
        "House deposit: needed each month",
    ),
    "assumed_return": Fact(
        "bps", _assumption("expected_real_return_bps"), "The stated real return (the default)"
    ),
    # retirement (ticket 118): the band's endpoints and the earliest 90% year, from the engine
    "fire_success_low_rate": Fact("bps", _band_rate(300), "Success at a 3% withdrawal rate"),
    "fire_success_4pct": Fact("bps", _band_rate(400), "Success at a 4% withdrawal rate"),
    "fire_success_high_rate": Fact("bps", _band_rate(450), "Success at a 4.5% withdrawal rate"),
    "fire_earliest_year": Fact("count", _earliest_year, "The earliest year reaching 90%"),
    "fire_save_500_year": Fact(
        "count",
        _what_if_year("extra_monthly_saving", 50_000),
        "The earliest 90% year saving $500 more a month",
    ),
    "fire_spend_cut_year": Fact(
        "count",
        _what_if_year("spend_change_bps", -1000),
        "The earliest 90% year spending 10% less",
    ),
}


def compute_all(session: Session, today: dt.date) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with synthetic_returns():
        for name, fact in FACTS.items():
            value = fact.compute(session, today)
            if isinstance(value, dt.date):
                value = value.isoformat()
            out[name] = {"unit": fact.unit, "value": value}
    return out
