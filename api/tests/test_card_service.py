"""`services/cards.py`, called directly: the reading the Cards screen and the advisor share.

Ticket 082 moved this out of `routers/cards.py`; `test_cards.py` still covers it through
HTTP, unchanged. These pin the service's own answers with figures worked out by hand, so a
tool calling it cannot be told something the screen would not show.

One monthly $15.00 credit anchored 1 January 2026, evaluated on 10 June:

| Month | Recorded |
|---|---|
| Jan, Feb, Apr | nothing — missed |
| Mar | one tap: full $15.00 |
| May | partial: $10.00 |
| Jun | current period, unused, 20 days left |
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import PerkCadence
from app.services import cards

ON = dt.date(2026, 6, 10)


@pytest.fixture
def card_id(make_account: Callable[..., int]) -> int:
    return make_account(name="Sapphire", kind="liability", subtype="credit_card")


@pytest.fixture
def monthly(db_session: Session, card_id: int) -> CardPerk:
    perk = CardPerk(
        account_id=card_id,
        name="Dining credit",
        value=Decimal("15.00"),
        cadence=PerkCadence.MONTHLY,
        anchor_on=dt.date(2026, 1, 1),
    )
    db_session.add(perk)
    db_session.flush()
    db_session.add_all(
        [
            PerkRedemption(perk_id=perk.id, period_start=dt.date(2026, 3, 1)),
            PerkRedemption(
                perk_id=perk.id, period_start=dt.date(2026, 5, 1), amount=Decimal("10.00")
            ),
        ]
    )
    db_session.flush()
    return perk


def test_the_current_period_is_resolved(db_session: Session, monthly: CardPerk) -> None:
    view = cards.perk_view(db_session, monthly, ON)

    assert view.current is not None
    assert (view.current.start, view.current.end) == (dt.date(2026, 6, 1), dt.date(2026, 7, 1))
    assert view.current.days_remaining == 20
    assert view.current.is_used is False
    assert view.current.is_urgent is False
    assert view.is_unused_now


def test_a_perk_whose_first_period_is_ahead_has_no_current_period(
    db_session: Session, card_id: int
) -> None:
    perk = CardPerk(
        account_id=card_id,
        name="Hotel credit",
        value=Decimal("50.00"),
        cadence=PerkCadence.ANNUAL,
        anchor_on=dt.date(2026, 9, 1),
    )
    db_session.add(perk)
    db_session.flush()

    assert cards.perk_view(db_session, perk, ON).current is None


def test_realised_counts_a_partial_at_its_amount_and_a_tap_at_face_value(
    db_session: Session, card_id: int, monthly: CardPerk
) -> None:
    assert cards.realised_this_year(db_session, card_id, ON) == Decimal("25.00")


def test_history_reports_realised_value_and_missed_periods(
    db_session: Session, monthly: CardPerk
) -> None:
    result = cards.history(
        db_session, perk_id=monthly.id, from_date=dt.date(2026, 1, 1), to_date=None, today=ON
    )

    assert [e.redemption.period_start for e in result.entries] == [
        dt.date(2026, 5, 1),
        dt.date(2026, 3, 1),
    ]
    assert [e.realised for e in result.entries] == [Decimal("10.00"), Decimal("15.00")]
    assert result.realised == Decimal("25.00")
    # January, February and April ended with nothing recorded. June is still spendable.
    assert result.missed_periods == 3


def test_the_card_totals_count_only_active_unused_perks(
    db_session: Session, card_id: int, monthly: CardPerk
) -> None:
    db_session.add(
        CardPerk(
            account_id=card_id,
            name="Retired credit",
            value=Decimal("99.00"),
            cadence=PerkCadence.MONTHLY,
            anchor_on=dt.date(2026, 1, 1),
            is_active=False,
        )
    )
    db_session.flush()

    card = next(c for c in cards.list_cards(db_session, ON) if c.account.id == card_id)

    assert card.unused == Decimal("15.00")
    assert card.active_perk_count == 1
    assert card.realised_this_year == Decimal("25.00")


def test_upcoming_is_windowed_and_flags_urgency(db_session: Session, monthly: CardPerk) -> None:
    near_the_end = dt.date(2026, 6, 28)  # two days left in June

    soon = cards.upcoming(db_session, within_days=30, on=near_the_end)
    assert [i.view.perk.id for i in soon.items] == [monthly.id]
    assert soon.total == Decimal("15.00")
    assert soon.urgent == Decimal("15.00")

    assert cards.upcoming(db_session, within_days=1, on=near_the_end).items == []


def test_upcoming_leaves_out_a_used_period(db_session: Session, monthly: CardPerk) -> None:
    db_session.add(PerkRedemption(perk_id=monthly.id, period_start=dt.date(2026, 6, 1)))
    db_session.flush()

    assert cards.upcoming(db_session, within_days=30, on=ON).items == []
