"""Debt analysis: the schedule to the cent, avalanche against snowball, prepay against invest,
utilisation, the two findings and the two tools."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.enums import AccountSubtype
from app.models.liability_terms import LiabilityTerms
from app.models.planning import PlanningAssumptions
from app.schemas.advisor import FindingKind
from app.schemas.common import ViewScope
from app.services import findings as findings_service
from app.services.analysis import debt
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake
from app.services.perks import add_months

JAN = dt.date(2026, 1, 1)
TODAY = dt.date(2026, 8, 18)


def _debt(
    balance: str,
    apr: str,
    payment: str,
    *,
    account_id: int = 1,
    promo_apr: str | None = None,
    promo_ends_on: dt.date | None = None,
) -> debt.Debt:
    return debt.Debt(
        account_id=account_id,
        name=f"Debt {account_id}",
        subtype=AccountSubtype.PERSONAL_LOAN,
        balance=Decimal(balance),
        apr=Decimal(apr),
        payment=Decimal(payment),
        payment_source="minimum",
        promo_apr=None if promo_apr is None else Decimal(promo_apr),
        promo_ends_on=promo_ends_on,
    )


# ── the schedule ──────────────────────────────────────────────────────────────


def test_a_known_loan_amortises_to_the_cent() -> None:
    # $1,000 at 12% (1% a month), $100 a month. Worked by hand, interest rounded half-up
    # each month as a statement does:
    #   1  10.00  → 910.00      5  6.35 → 540.91      9  2.54 → 156.83
    #   2   9.10  → 819.10      6  5.41 → 446.32     10  1.57 →  58.40
    #   3   8.19  → 727.29      7  4.46 → 350.78     11  0.58 →   0.00 (pays 58.98)
    #   4   7.27  → 634.56      8  3.51 → 254.29
    schedule = debt.amortise(_debt("1000.00", "12", "100.00"), TODAY, Decimal("100.00"))

    assert [str(m.interest) for m in schedule.months] == [
        "10.00", "9.10", "8.19", "7.27", "6.35", "5.41", "4.46", "3.51", "2.54", "1.57", "0.58",
    ]  # fmt: skip
    assert [str(m.balance) for m in schedule.months][:4] == ["910.00", "819.10", "727.29", "634.56"]
    assert schedule.months[-1].payment == Decimal("58.98")
    assert schedule.months[-1].balance == 0
    assert schedule.total_interest == Decimal("58.98")
    assert schedule.paid_off_month == 11
    assert schedule.months[0].paid_on == dt.date(2026, 9, 18)


def test_interest_rounds_half_up_each_month() -> None:
    # 100.50 at 1% = 1.005: half-up gives 1.01 where banker's rounding would give 1.00.
    assert debt.monthly_interest(Decimal("100.50"), Decimal("12")) == Decimal("1.01")
    assert debt.monthly_interest(Decimal("100.49"), Decimal("12")) == Decimal("1.00")


def test_a_promotion_that_ends_mid_schedule() -> None:
    ends = add_months(TODAY, 3)
    loan = _debt("1200.00", "12", "100.00", promo_apr="0", promo_ends_on=ends)

    schedule = debt.amortise(loan, TODAY, loan.payment)

    assert [m.interest for m in schedule.months[:3]] == [Decimal("0.00")] * 3
    assert schedule.months[2].balance == Decimal("900.00")
    assert schedule.months[3].paid_on == add_months(TODAY, 4)
    assert schedule.months[3].interest == Decimal("9.00")  # 1% of 900, the promotion over


def test_a_payment_below_the_interest_never_pays_off() -> None:
    schedule = debt.amortise(_debt("10000.00", "24", "150.00"), TODAY, Decimal("150.00"))

    assert schedule.paid_off_month is None
    assert len(schedule.months) == debt.MAX_MONTHS


def test_a_level_payment_clears_the_balance_on_time() -> None:
    payment = debt.level_payment(Decimal("10000.00"), Decimal("6"), 36)

    schedule = debt.amortise(_debt("10000.00", "6", str(payment)), TODAY, payment)

    assert payment == Decimal("304.22")  # 304.2194…, rounded up so the last is not larger
    assert schedule.paid_off_month == 36
    assert schedule.months[-1].payment <= payment


# ── avalanche and snowball ────────────────────────────────────────────────────


THREE = [
    _debt("2000.00", "24", "60.00", account_id=1),  # dearest
    _debt("500.00", "18", "25.00", account_id=2),  # smallest
    _debt("8000.00", "6", "200.00", account_id=3),
]


def test_avalanche_and_snowball_order_differently() -> None:
    assert [d.account_id for d in debt.order_for("avalanche", THREE)] == [1, 2, 3]
    assert [d.account_id for d in debt.order_for("snowball", THREE)] == [2, 1, 3]


def test_avalanche_costs_no_more_interest_than_snowball() -> None:
    avalanche = debt.plan("avalanche", THREE, Decimal("200.00"), TODAY)
    snowball = debt.plan("snowball", THREE, Decimal("200.00"), TODAY)

    assert avalanche.total_interest < snowball.total_interest
    assert avalanche.months_to_debt_free is not None
    assert snowball.months_to_debt_free is not None
    # Snowball clears the small debt first; avalanche the dear one.
    first = {p.account_id: p.month for p in snowball.payoffs}
    assert first[2] is not None and first[1] is not None and first[2] < first[1]
    dearest = {p.account_id: p.month for p in avalanche.payoffs}
    assert dearest[1] is not None and dearest[1] < snowball.payoffs[1].month  # type: ignore[operator]


def test_every_dollar_of_the_budget_is_accounted_for() -> None:
    extra = Decimal("200.00")
    plan = debt.plan("avalanche", THREE, extra, TODAY)
    owed = sum((d.balance for d in THREE), Decimal(0))
    budget = sum((d.payment for d in THREE), Decimal(0)) + extra

    assert plan.months_to_debt_free is not None
    # Everything paid is the balances plus their interest, and never more than the budget.
    assert owed + plan.total_interest <= budget * plan.months_to_debt_free
    assert owed + plan.total_interest > budget * (plan.months_to_debt_free - 1)


# ── from the database ─────────────────────────────────────────────────────────


@pytest.fixture
def owe(db_session: Session, make_account: Callable[..., int], owner_id: int) -> Callable[..., int]:
    def _owe(
        name: str,
        subtype: str,
        balance: str,
        terms: dict[str, Any] | None = None,
        on: dt.date = TODAY,
    ) -> int:
        account = make_account(name=name, kind="liability", subtype=subtype)
        create_initial_stake(db_session, account, owner_id, JAN)
        record_balance(db_session, account, on, Decimal(balance))
        if terms is not None:
            db_session.add(LiabilityTerms(account_id=account, as_of=TODAY, **terms))
        db_session.flush()
        return account

    return _owe


def test_a_debt_with_no_terms_is_a_limitation_never_zero_percent(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    card = owe(
        "Card",
        "credit_card",
        "1250.00",
        {"apr": Decimal("24.99"), "minimum_payment": Decimal("35")},
    )
    loan = owe("Family loan", "personal_loan", "3000.00")
    maturity_less = owe("Old loan", "personal_loan", "900.00", {"apr": Decimal("5")})

    owed, limited = debt.debts(db_session, TODAY, owner_id)

    assert [d.account_id for d in owed] == [card]
    assert {(item.account_id, item.reason) for item in limited} == {
        (loan, "no_terms"),
        (maturity_less, "no_payment"),
    }
    comparison = debt.strategies(db_session, TODAY, owner_id, Decimal("100"))
    assert [p.account_id for p in comparison.avalanche.payoffs] == [card]
    assert len(comparison.limitations) == 2


def test_a_payment_is_derived_from_the_maturity_date(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    owe(
        "Car",
        "auto_loan",
        "10000.00",
        {"apr": Decimal("6"), "maturity_on": add_months(TODAY, 36)},
    )

    (car,), _ = debt.debts(db_session, TODAY, owner_id)

    assert (car.payment, car.payment_source) == (Decimal("304.22"), "level_to_maturity")


def _assume(db_session: Session, real_bps: int, inflation_bps: int) -> None:
    default = db_session.execute(
        select(PlanningAssumptions).where(PlanningAssumptions.is_default)
    ).scalar_one()
    fields = {
        column.key: getattr(default, column.key)
        for column in PlanningAssumptions.__table__.columns
        if column.key not in {"id", "effective_from", "is_default"}
    }
    fields.update(expected_real_return_bps=real_bps, inflation_bps=inflation_bps)
    db_session.add(
        PlanningAssumptions(
            **fields,
            is_default=False,
            effective_from=default.effective_from + dt.timedelta(days=1),
        )
    )
    db_session.flush()


def test_with_no_return_prepaying_wins_by_exactly_the_interest_saved(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    loan = owe(
        "Loan", "personal_loan", "5000.00", {"apr": Decimal("7"), "minimum_payment": Decimal("150")}
    )
    _assume(db_session, 0, 0)

    result = debt.prepay_vs_invest(db_session, TODAY, owner_id, loan, Decimal("200"), 5)

    assert isinstance(result, debt.PrepayOrInvest)
    assert result.assumptions.nominal_return_bps == 0
    assert result.interest_saved > 0
    assert result.difference == -result.interest_saved
    for path in (result.prepay, result.invest):
        # The same money each month, spent two ways: every dollar is on the debt or invested.
        paid_on_debt = Decimal("5000.00") + path.interest_paid - path.debt_left
        assert paid_on_debt + path.invested == Decimal("350") * 60
    assert result.prepay.debt_free_month is not None and result.invest.debt_free_month is not None
    assert result.prepay.debt_free_month < result.invest.debt_free_month
    assert "Mortgage-interest deductibility is not modelled." in result.exclusions


def test_a_high_return_on_a_cheap_loan_favours_investing(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    loan = owe(
        "Mortgage",
        "mortgage",
        "200000.00",
        {"apr": Decimal("3"), "minimum_payment": Decimal("1200")},
    )
    _assume(db_session, 700, 250)

    result = debt.prepay_vs_invest(db_session, TODAY, owner_id, loan, Decimal("500"), 20)

    assert isinstance(result, debt.PrepayOrInvest)
    assert result.assumptions.nominal_return_bps == 968  # 1.07 x 1.025 - 1 = 9.675%, half-up
    assert result.difference > 0


def test_prepay_reports_a_limitation_or_nothing(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    bare = owe("Family loan", "personal_loan", "3000.00")

    assert debt.prepay_vs_invest(db_session, TODAY, owner_id, bare, Decimal("100"), 5) == (
        debt.Limitation(bare, "Family loan", "no_terms")
    )
    assert debt.prepay_vs_invest(db_session, TODAY, owner_id, 999_999, Decimal("100"), 5) is None
    with pytest.raises(ValueError, match="1 to 40"):
        debt.prepay_vs_invest(db_session, TODAY, owner_id, bare, Decimal("100"), 41)


def test_utilisation_per_card_and_overall(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    low = owe(
        "Low", "credit_card", "1250.00", {"apr": Decimal("20"), "credit_limit": Decimal("5000")}
    )
    high = owe(
        "High", "credit_card", "2000.00", {"apr": Decimal("20"), "credit_limit": Decimal("5000")}
    )
    unknown = owe("No limit", "credit_card", "300.00", {"apr": Decimal("20")})

    result = debt.utilisation(db_session, TODAY, owner_id)

    assert {c.account_id: c.bps for c in result.cards} == {low: 2500, high: 4000}
    assert result.overall_bps == 3250  # 3,250 of 10,000
    assert result.without_limit == [unknown]


# ── findings ──────────────────────────────────────────────────────────────────


def _kinds(db_session: Session, owner_id: int, kind: FindingKind) -> dict[str, Any]:
    return {
        f.id: f
        for f in findings_service.findings(db_session, TODAY, ViewScope.MINE, owner_id)
        if f.kind is kind
    }


def test_high_interest_debt_at_8_percent_and_500_dollars(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    dear = owe("Card", "credit_card", "1250.00", {"apr": Decimal("24.990")})
    owe("Cheap", "auto_loan", "9000.00", {"apr": Decimal("7.990")})
    owe("Small", "credit_card", "499.99", {"apr": Decimal("29.99")})
    owe(
        "Promo",
        "credit_card",
        "3000.00",
        {"apr": Decimal("22"), "promo_apr": Decimal("0"), "promo_ends_on": add_months(TODAY, 6)},
    )
    edge = owe("Edge", "personal_loan", "500.00", {"apr": Decimal("8")})

    found = _kinds(db_session, owner_id, FindingKind.HIGH_INTEREST_DEBT)

    assert set(found) == {f"high_interest_debt:acct{dear}", f"high_interest_debt:acct{edge}"}
    card = found[f"high_interest_debt:acct{dear}"]
    assert card.title == "Card charges 24.99% on $1,250.00"
    assert [(e.label, e.value_cents or e.value_bps) for e in card.evidence] == [
        ("Balance", 125_000),
        ("APR", 2499),
        ("A year's interest", 31_238),  # 312.375 → 312.38
    ]


def test_credit_utilisation_high_above_30_percent(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    owe("At 30", "credit_card", "1500.00", {"apr": Decimal("20"), "credit_limit": Decimal("5000")})
    high = owe(
        "High", "credit_card", "2000.00", {"apr": Decimal("20"), "credit_limit": Decimal("5000")}
    )

    found = _kinds(db_session, owner_id, FindingKind.CREDIT_UTILISATION_HIGH)

    assert list(found) == [f"credit_utilisation_high:acct{high}"]
    assert found[f"credit_utilisation_high:acct{high}"].title == "High is using 40% of its limit"


# ── the tools ─────────────────────────────────────────────────────────────────


def _ctx(db_session: Session, owner_id: int) -> ToolContext:
    return ToolContext(
        today=TODAY,
        user_id=owner_id,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )


def test_debt_compare_strategies_returns_both_sides_and_the_gaps(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    owe("Card", "credit_card", "2000.00", {"apr": Decimal("24"), "minimum_payment": Decimal("60")})
    owe(
        "Store card",
        "credit_card",
        "500.00",
        {"apr": Decimal("18"), "minimum_payment": Decimal("25")},
    )
    owe("Family loan", "personal_loan", "3000.00")

    outcome = load_all().run(
        "debt_compare_strategies",
        {"extra_monthly_cents": 20_000, "view": None},
        _ctx(db_session, owner_id),
    )

    assert outcome.status == "ok"
    content = outcome.content
    assert '"strategy":"avalanche"' in content and '"strategy":"snowball"' in content
    assert "[c1.avalanche.total_interest]" in content
    assert "[c1.interest_difference]" in content
    assert '"reason":"no_terms"' in content


def test_debt_prepay_vs_invest_states_its_assumptions(
    db_session: Session, owe: Callable[..., int], owner_id: int
) -> None:
    loan = owe(
        "Loan",
        "personal_loan",
        "5000.00",
        {"apr": Decimal("6.875"), "minimum_payment": Decimal("150")},
    )

    outcome = load_all().run(
        "debt_prepay_vs_invest",
        {"account_id": loan, "extra_monthly_cents": 20_000, "horizon_years": 10, "view": None},
        _ctx(db_session, owner_id),
    )

    assert outcome.status == "ok"
    content = outcome.content
    assert "6.875% [c1.apr_pct]" in content
    assert "[c1.assumptions.real_return_pct]" in content
    assert "Mortgage-interest deductibility is not modelled." in content
    assert "[c1.difference]" in content


@pytest.mark.parametrize(
    "args",
    [
        {"extra_monthly_cents": 20_000, "horizon_years": 41},
        {"extra_monthly_cents": 20_000, "horizon_years": 0},
        {"extra_monthly_cents": 99, "horizon_years": 10},
        {"extra_monthly_cents": 10_000_001, "horizon_years": 10},
    ],
)
def test_prepay_arguments_are_bounded(
    db_session: Session, owe: Callable[..., int], owner_id: int, args: dict[str, int]
) -> None:
    loan = owe(
        "Loan", "personal_loan", "5000.00", {"apr": Decimal("6"), "minimum_payment": Decimal("150")}
    )

    outcome = load_all().run(
        "debt_prepay_vs_invest",
        {"account_id": loan, "view": None, **args},
        _ctx(db_session, owner_id),
    )

    assert outcome.status == "invalid_args"


def test_prepay_on_an_unknown_debt_is_invalid(db_session: Session, owner_id: int) -> None:
    outcome = load_all().run(
        "debt_prepay_vs_invest",
        {"account_id": 999_999, "extra_monthly_cents": 20_000, "horizon_years": 10, "view": None},
        _ctx(db_session, owner_id),
    )

    assert outcome.status == "invalid_args"
    assert "debt_terms" in outcome.content
