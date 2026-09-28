"""The findings engine: each kind at its threshold, ranking, and the stale-evidence rule.

Each test builds the smallest world that should — or should not — produce a finding, and
names the day. The thresholds are the constants at the top of `services/findings.py`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import PerkCadence
from app.schemas.advisor import ActionKind, Finding, FindingKind, Screen, Severity
from app.schemas.common import ViewScope
from app.services import findings as engine
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake

D = dt.date
Tx = Callable[..., int]
Make = Callable[..., int]
NEW_YEAR = D(2026, 1, 1)


def kinds(found: list[Finding]) -> list[FindingKind]:
    return [f.kind for f in found]


@pytest.fixture
def account(db_session: Session, make_account: Make, owner_id: int) -> Callable[..., int]:
    """An account with a 100% stake and, optionally, a balance."""

    def _make(
        name: str,
        kind: str = "liquid_asset",
        subtype: str = "checking",
        balance: str | None = None,
        on: dt.date = NEW_YEAR,
    ) -> int:
        account_id = make_account(name=name, kind=kind, subtype=subtype)
        create_initial_stake(db_session, account_id, owner_id, D(2025, 1, 1), Decimal("100"))
        if balance is not None:
            record_balance(db_session, account_id, on, Decimal(balance))
        return account_id

    return _make


# ── perk_expiring ─────────────────────────────────────────────────────────────


@pytest.fixture
def dining(db_session: Session, make_account: Make) -> CardPerk:
    card = make_account(name="Sapphire", kind="liability", subtype="credit_card")
    perk = CardPerk(
        account_id=card,
        name="Dining",
        value=Decimal("15.00"),
        cadence=PerkCadence.MONTHLY,
        anchor_on=D(2026, 1, 1),
    )
    db_session.add(perk)
    db_session.flush()
    return perk


def test_an_urgent_unused_credit(db_session: Session, dining: CardPerk) -> None:
    found = engine._perks_expiring(db_session, D(2026, 6, 25))

    assert kinds(found) == [FindingKind.PERK_EXPIRING]
    assert found[0].severity is Severity.URGENT
    assert found[0].title == "Dining on Sapphire: $15.00 lapses in 6 days"
    assert found[0].action is not None and found[0].action.perk_id == dining.id


def test_not_yet_urgent_or_already_used(db_session: Session, dining: CardPerk) -> None:
    assert engine._perks_expiring(db_session, D(2026, 6, 20)) == []  # ten days left
    db_session.add(PerkRedemption(perk_id=dining.id, period_start=D(2026, 6, 1)))
    db_session.flush()
    assert engine._perks_expiring(db_session, D(2026, 6, 25)) == []


# ── data health: transfers, uncategorised, quiet imports ──────────────────────


def test_a_likely_unmarked_transfer(
    db_session: Session, account: Callable[..., int], make_transaction: Tx
) -> None:
    checking, savings = account("Checking"), account("Savings", subtype="savings")
    out = make_transaction(checking, D(2026, 3, 10), "-1500.00", "TO SAVINGS")
    into = make_transaction(savings, D(2026, 3, 11), "1500.00", "FROM CHECKING")

    found = [
        f
        for f in engine._health_findings(db_session, D(2026, 4, 1))
        if f.kind is FindingKind.POSSIBLE_UNMARKED_TRANSFER
    ]

    assert len(found) == 1
    assert found[0].severity is Severity.WARNING
    assert found[0].action is not None
    assert found[0].action.kind is ActionKind.MARK_TRANSFER
    assert found[0].action.transaction_ids == [out, into]


@pytest.mark.parametrize(
    ("uncategorised", "categorised", "expected"),
    [
        ("-61.00", "-40.00", True),  # 60.4% of March
        ("-4.00", "-96.00", False),  # 4%: under the 5% threshold
    ],
)
def test_uncategorised_share(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    category_ids: dict[str, int],
    uncategorised: str,
    categorised: str,
    expected: bool,
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    make_transaction(card, D(2026, 3, 10), uncategorised, "X")
    make_transaction(card, D(2026, 3, 11), categorised, "GROCER", category_ids["Groceries"])

    found = kinds(engine._health_findings(db_session, D(2026, 4, 15)))

    assert (FindingKind.UNCATEGORISED_SPEND in found) is expected


def test_ten_uncategorised_rows_are_enough_whatever_the_share(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    category_ids: dict[str, int],
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    for day in range(1, 11):
        make_transaction(card, D(2026, 3, day), "-0.10", f"TINY {day}")
    make_transaction(card, D(2026, 3, 20), "-5000.00", "RENT", category_ids["Rent or Mortgage"])

    assert FindingKind.UNCATEGORISED_SPEND in kinds(
        engine._health_findings(db_session, D(2026, 4, 15))
    )


@pytest.mark.parametrize(("days", "expected"), [(35, False), (36, True)])
def test_quiet_imports(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    days: int,
    expected: bool,
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    today = D(2026, 4, 15)
    make_transaction(card, today - dt.timedelta(days=days), "-10.00", "X")

    found = kinds(engine._health_findings(db_session, today))

    assert (FindingKind.TRANSACTIONS_NOT_IMPORTED in found) is expected


# ── balances: stale, runway, net worth ────────────────────────────────────────


def test_a_stale_balance_keeps_its_severity(
    db_session: Session, account: Callable[..., int], owner_id: int
) -> None:
    account("Brokerage", subtype="brokerage", balance="50000", on=D(2026, 1, 14))

    found = engine._stale_balances(db_session, D(2026, 4, 15), owner_id)

    assert kinds(found) == [FindingKind.STALE_BALANCE]
    assert found[0].severity is Severity.WARNING
    assert found[0].action is not None and found[0].action.screen is Screen.ACCOUNT
    assert found[0].title == "Brokerage's balance is 91 days old"


@pytest.fixture
def burn(account: Callable[..., int], make_transaction: Tx, category_ids: dict[str, int]) -> None:
    """$1,000 of groceries in each of the six months before July 2026."""
    card = account("Card", kind="liability", subtype="credit_card")
    for month in range(1, 7):
        make_transaction(card, D(2026, month, 10), "-1000.00", "GROCER", category_ids["Groceries"])


@pytest.mark.parametrize(("liquid", "expected"), [("2000", True), ("3000", False)])
def test_runway_low_is_strictly_under_three_months(
    db_session: Session,
    account: Callable[..., int],
    owner_id: int,
    burn: None,
    liquid: str,
    expected: bool,
) -> None:
    account("Checking", balance=liquid, on=D(2026, 7, 1))

    found = engine._runway_low(db_session, D(2026, 7, 5), owner_id)

    assert bool(found) is expected
    if found:
        assert found[0].severity is Severity.WARNING
        assert found[0].title == "Liquid assets cover 2.0 months of spending"


def test_stale_evidence_demotes_and_redirects(
    db_session: Session, account: Callable[..., int], owner_id: int, burn: None
) -> None:
    account("Checking", balance="2000", on=D(2026, 3, 1))  # 126 days old on 5 July

    found = engine._runway_low(db_session, D(2026, 7, 5), owner_id)

    assert found[0].stale is True
    assert found[0].severity is Severity.NOTICE
    assert found[0].action is not None
    assert found[0].action.kind is ActionKind.UPDATE_BALANCE
    assert "update it first" in found[0].detail


@pytest.mark.parametrize(("now", "expected"), [("94000", True), ("95000", False)])
def test_net_worth_drop_must_exceed_five_percent(
    db_session: Session, account: Callable[..., int], owner_id: int, now: str, expected: bool
) -> None:
    checking = account("Checking", balance="100000", on=D(2026, 5, 1))
    record_balance(db_session, checking, D(2026, 6, 1), Decimal(now))

    assert bool(engine._net_worth_drop(db_session, D(2026, 6, 5), owner_id)) is expected


# ── spending ──────────────────────────────────────────────────────────────────


def test_a_spending_spike(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    category_ids: dict[str, int],
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    for month in range(1, 7):
        make_transaction(card, D(2026, month, 5), "-100.00", "BISTRO", category_ids["Restaurants"])
    make_transaction(card, D(2026, 7, 5), "-400.00", "BISTRO", category_ids["Restaurants"])

    found = engine._spend_spikes(db_session, D(2026, 8, 10))

    assert kinds(found) == [FindingKind.SPEND_SPIKE]
    assert found[0].title == "Restaurants was $300.00 above usual in July"
    assert found[0].impact_cents == 30_000


def test_a_quarter_up_like_for_like(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    category_ids: dict[str, int],
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    make_transaction(card, D(2026, 4, 10), "-400.00", "X", category_ids["Groceries"])
    make_transaction(card, D(2026, 7, 10), "-600.00", "X", category_ids["Groceries"])

    found = engine._spend_increase(db_session, D(2026, 7, 20))

    assert kinds(found) == [FindingKind.SPEND_INCREASE]
    assert found[0].severity is Severity.INFO


def test_a_price_increase_and_the_summary(
    db_session: Session,
    account: Callable[..., int],
    make_transaction: Tx,
    category_ids: dict[str, int],
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    for month in range(1, 9):
        price = "17.99" if month >= 8 else "15.49"
        make_transaction(
            card, D(2026, month, 3), f"-{price}", "STREAMLY", category_ids["Subscriptions"]
        )

    found = engine._recurring(db_session, D(2026, 8, 20))

    assert kinds(found) == [FindingKind.RECURRING_PRICE_INCREASE, FindingKind.RECURRING_SUMMARY]
    assert found[0].title == "STREAMLY went up $2.50 per monthly charge"
    assert found[0].impact_cents == 3_000


# ── card fees ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("renews_in", "expected"), [(60, True), (61, False)])
def test_a_fee_renewing_soon_and_not_covered(
    db_session: Session, make_account: Make, renews_in: int, expected: bool
) -> None:
    today = D(2026, 6, 28)
    card_id = make_account(name="Sapphire", kind="liability", subtype="credit_card")
    card = db_session.get(Account, card_id)
    assert card is not None
    card.annual_fee = Decimal("95.00")
    card.fee_renews_on = today + dt.timedelta(days=renews_in)
    db_session.flush()

    assert bool(engine._fees_uncovered(db_session, today)) is expected


# ── the engine ────────────────────────────────────────────────────────────────


def test_ranking_and_stable_ids(
    db_session: Session,
    dining: CardPerk,
    account: Callable[..., int],
    owner_id: int,
    make_transaction: Tx,
) -> None:
    account("Brokerage", subtype="brokerage", balance="50000", on=D(2026, 1, 1))
    checking, savings = account("Checking"), account("Savings", subtype="savings")
    make_transaction(checking, D(2026, 6, 10), "-1500.00", "OUT")
    make_transaction(savings, D(2026, 6, 11), "1500.00", "IN")
    today = D(2026, 6, 25)

    first = engine.findings(db_session, today, ViewScope.MINE, owner_id)
    second = engine.findings(db_session, today, ViewScope.MINE, owner_id)

    severities = [f.severity for f in first]
    assert severities[0] is Severity.URGENT
    order = {Severity.URGENT: 0, Severity.WARNING: 1, Severity.NOTICE: 2, Severity.INFO: 3}
    assert [order[s] for s in severities] == sorted(order[s] for s in severities)
    warnings = [f for f in first if f.severity is Severity.WARNING]
    # $50,000 stale brokerage ranks above a $1,500 transfer.
    assert [f.kind for f in warnings] == [
        FindingKind.STALE_BALANCE,
        FindingKind.POSSIBLE_UNMARKED_TRANSFER,
    ]
    assert [f.id for f in first] == [f.id for f in second]


def test_spend_findings_are_the_same_in_both_views(
    db_session: Session,
    account: Callable[..., int],
    owner_id: int,
    make_transaction: Tx,
    category_ids: dict[str, int],
) -> None:
    card = account("Card", kind="liability", subtype="credit_card")
    for month in range(1, 7):
        make_transaction(card, D(2026, month, 5), "-100.00", "BISTRO", category_ids["Restaurants"])
    make_transaction(card, D(2026, 7, 5), "-400.00", "BISTRO", category_ids["Restaurants"])
    today = D(2026, 8, 10)
    spend_kinds = {
        FindingKind.SPEND_SPIKE,
        FindingKind.SPEND_INCREASE,
        FindingKind.UNCATEGORISED_SPEND,
    }

    mine = [
        f
        for f in engine.findings(db_session, today, ViewScope.MINE, owner_id)
        if f.kind in spend_kinds
    ]
    household = [
        f
        for f in engine.findings(db_session, today, ViewScope.HOUSEHOLD, owner_id)
        if f.kind in spend_kinds
    ]

    assert mine == household
    assert mine
