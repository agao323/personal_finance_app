"""Tests for the ownership-adjusted net worth calculation.

Every expected value here is computed by hand in the test's own comment. Deriving them
from the implementation's output would make the suite agree with whatever the code
does, which is precisely the failure mode that matters for a number nobody can eyeball.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.enums import AccountKind
from app.services.balances import record_balance
from app.services.net_worth import net_worth
from app.services.ownership import adjust, create_initial_stake, transition_stake

JAN = dt.date(2026, 1, 1)
MAR = dt.date(2026, 3, 1)
JUN = dt.date(2026, 6, 1)
SEP = dt.date(2026, 9, 1)


def _money(value: str) -> Decimal:
    return Decimal(value)


# ── the basics ────────────────────────────────────────────────────────────────


def test_single_fully_owned_asset(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("1000.00"))

    result = net_worth(db_session, MAR, owner_id)

    assert result.net_worth == _money("1000.00")
    assert result.assets == _money("1000.00")
    assert result.liabilities == _money("0.00")


def test_liabilities_subtract_and_stay_positive(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Liabilities are stored positive; net worth subtracts them.

    Assets 10,000 - liabilities 2,500 = 7,500.
    """
    asset = make_account(name="Savings")
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    for account_id in (asset, card):
        create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, asset, JAN, _money("10000.00"))
    record_balance(db_session, card, JAN, _money("2500.00"))

    result = net_worth(db_session, MAR, owner_id)

    assert result.assets == _money("10000.00")
    assert result.liabilities == _money("2500.00")  # positive
    assert result.net_worth == _money("7500.00")


def test_breakdown_by_kind(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    liquid = make_account(name="Checking")
    house = make_account(name="House", kind="illiquid_asset", subtype="real_estate")
    loan = make_account(name="Mortgage", kind="liability", subtype="mortgage")
    for account_id in (liquid, house, loan):
        create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, liquid, JAN, _money("5000.00"))
    record_balance(db_session, house, JAN, _money("400000.00"))
    record_balance(db_session, loan, JAN, _money("250000.00"))

    result = net_worth(db_session, MAR, owner_id)

    assert result.by_kind[AccountKind.LIQUID_ASSET] == _money("5000.00")
    assert result.by_kind[AccountKind.ILLIQUID_ASSET] == _money("400000.00")
    assert result.by_kind[AccountKind.LIABILITY] == _money("250000.00")
    # 5,000 + 400,000 - 250,000
    assert result.net_worth == _money("155000.00")


def test_total_equals_the_sum_of_its_rows(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The reason rounding is per account rather than on the total.

    A case where the two orders genuinely disagree: 33.33% of 100.01 is 33.333333,
    which rounds to 33.33 — three of those sum to 99.99. Rounding the combined 300.03
    instead gives 99.999999 -> 100.00.

    Those differ by a cent, and 99.99 is the correct answer because it is what the
    three rows on screen add up to. A dashboard whose total does not match its own
    rows discredits every other number on the page.
    """
    ids = [make_account(name=f"A{i}") for i in range(3)]
    for account_id in ids:
        create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("33.33"))
        record_balance(db_session, account_id, JAN, _money("100.01"))

    result = net_worth(db_session, MAR, owner_id)

    rows = sum(c.adjusted_balance for c in result.contributions)
    assert result.net_worth == rows
    assert result.net_worth == _money("99.99")
    # Rounding the total instead would have produced this — the bug being prevented.
    assert adjust(_money("300.03"), Decimal("33.33")) == _money("100.00")


# ── in force on as_of ─────────────────────────────────────────────────────────


def test_uses_the_stake_in_force_not_todays(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The load-bearing case.

    100% until June, 50% after. A March reading must be the full 2,000.00, not the
    1,000.00 that today's stake would give.
    """
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("2000.00"))
    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("2000.00")
    assert net_worth(db_session, SEP, owner_id).net_worth == _money("1000.00")


def test_uses_the_snapshot_in_force_not_the_latest(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """A March reading uses January's balance, not June's."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("1000.00"))
    record_balance(db_session, account_id, JUN, _money("9999.00"))

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("1000.00")


def test_stake_and_snapshot_change_independently(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Both dimensions at once, which is where an off-by-one hides.

    Jan: 1,000 @ 100%  -> 1,000.00
    Mar: still Jan's balance, still 100%
    Jun: 4,000 @ 50%   -> 2,000.00
    """
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("1000.00"))
    record_balance(db_session, account_id, JUN, _money("4000.00"))
    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("1000.00")
    assert net_worth(db_session, JUN, owner_id).net_worth == _money("2000.00")


# ── exclusions ────────────────────────────────────────────────────────────────


def test_account_with_no_snapshot_yet_is_excluded_not_zero(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Zero would be a claim about the balance. Exclusion is the truth."""
    funded = make_account(name="Funded")
    future = make_account(name="Opened later")
    for account_id in (funded, future):
        create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, funded, JAN, _money("500.00"))
    record_balance(db_session, future, JUN, _money("100000.00"))

    result = net_worth(db_session, MAR, owner_id)

    assert result.net_worth == _money("500.00")
    assert [c.account_id for c in result.contributions] == [funded]


def test_closed_account_drops_out_on_its_close_date(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The sold-car case. Carry-forward would otherwise keep it indefinitely."""
    car = make_account(name="Car", kind="illiquid_asset", subtype="vehicle", closed_at=JUN)
    create_initial_stake(db_session, car, owner_id, JAN)
    record_balance(db_session, car, JAN, _money("15000.00"))

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("15000.00")
    assert net_worth(db_session, JUN, owner_id).net_worth == _money("0.00")
    assert net_worth(db_session, SEP, owner_id).contributions == []


def test_account_the_viewer_has_no_stake_in_is_excluded(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account(name="Partner's ISA")
    create_initial_stake(db_session, account_id, partner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("8000.00"))

    assert net_worth(db_session, MAR, owner_id).contributions == []
    assert net_worth(db_session, MAR, partner_id).net_worth == _money("8000.00")


# ── staleness ─────────────────────────────────────────────────────────────────


def test_stale_balance_is_included_and_counted(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Dropping it would make net worth silently fall the day it aged out."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, _money("1000.00"))

    fresh = net_worth(db_session, MAR, owner_id)
    assert fresh.stale_count == 0

    # January + 1 year is well past the 90-day carry-forward cap.
    stale = net_worth(db_session, dt.date(2027, 1, 1), owner_id)
    assert stale.net_worth == _money("1000.00")
    assert stale.stale_account_ids == [account_id]
    assert stale.stale_count == 1


# ── viewer vs household ───────────────────────────────────────────────────────


def test_household_sums_every_stake(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    """A jointly-held account: 60/40 to the two of you.

    Viewer sees 6,000.00; household sees the whole 10,000.00.
    """
    account_id = make_account(name="Joint")
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))
    create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("40"))
    record_balance(db_session, account_id, JAN, _money("10000.00"))

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("6000.00")
    assert net_worth(db_session, MAR, partner_id).net_worth == _money("4000.00")
    assert net_worth(db_session, MAR, None).net_worth == _money("10000.00")


def test_household_excludes_the_share_owned_outside_it(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """A 50%-owned rental: the other half belongs to someone else entirely.

    Household is 50% of 400,000 = 200,000 — not the full property value.
    """
    rental = make_account(name="Rental", kind="illiquid_asset", subtype="real_estate")
    create_initial_stake(db_session, rental, owner_id, JAN, Decimal("50"))
    record_balance(db_session, rental, JAN, _money("400000.00"))

    assert net_worth(db_session, MAR, None).net_worth == _money("200000.00")


def test_rounding_at_the_half_cent(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """50% of 1,234.57 is 617.285, which must round up to 617.29."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))
    record_balance(db_session, account_id, JAN, _money("1234.57"))

    assert net_worth(db_session, MAR, owner_id).net_worth == _money("617.29")


def test_empty_database_is_zero_not_an_error(db_session: Session, owner_id: int) -> None:
    result = net_worth(db_session, MAR, owner_id)

    assert result.net_worth == _money("0.00")
    assert result.contributions == []


@pytest.mark.parametrize("viewer", [True, False])
def test_contributions_report_raw_and_adjusted(
    db_session: Session, make_account: Callable[..., int], owner_id: int, viewer: bool
) -> None:
    """The UI shows both — that distinction is the feature."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))
    record_balance(db_session, account_id, JAN, _money("1000.00"))

    result = net_worth(db_session, MAR, owner_id if viewer else None)
    contribution = result.contributions[0]

    assert contribution.raw_balance == _money("1000.00")
    assert contribution.adjusted_balance == _money("500.00")
    assert contribution.percentage == Decimal("50.00")
    assert contribution.balance_as_of == JAN


def test_account_with_no_stake_rows_contributes_nothing(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Belt and braces on the household path.

    Every account is supposed to get an explicit 100% stake at creation, so this
    should be unreachable in practice. If it ever happens — a bad import, a manual
    insert — contributing nothing is the safe failure: the alternative would be
    silently treating an unowned account as fully owned.
    """
    account_id = make_account(name="Orphaned")
    record_balance(db_session, account_id, JAN, _money("5000.00"))

    result = net_worth(db_session, MAR, None)

    assert result.contributions == []
    assert result.net_worth == _money("0.00")
