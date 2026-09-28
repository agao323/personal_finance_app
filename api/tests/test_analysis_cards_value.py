"""Card value for 2026, on 28 June.

Sapphire, $95.00 fee:
- Dining $15.00 monthly from 1 January: six periods begun (Jan-Jun) = $90.00 available;
  March used in full, May $10.00 partial = $25.00 realised; Jan, Feb, Apr missed.
- Travel $200.00 annual from 1 January: one period, $200.00 available, unused, not yet missed.
- A retired perk, not counted as available.
Available $290.00, realised $25.00, 8.62% used, net -$70.00.

Plain, no fee recorded, no perks: realised $0.00, net $0.00, utilisation none.

Hotel, anchored on the cardmember year (1 March 2025, annual $300): the period that began in
March 2025 belongs to 2025, so 2026 has one period begun, on 1 March 2026.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import PerkCadence
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope
from app.services import cards as card_service
from app.services.analysis.cards_value import value

TODAY = dt.date(2026, 6, 28)
JAN = dt.date(2026, 1, 1)


@pytest.fixture
def cards(db_session: Session, make_account: Callable[..., int]) -> dict[str, int]:
    ids = {
        "sapphire": make_account(name="Sapphire", kind="liability", subtype="credit_card"),
        "plain": make_account(name="Plain", kind="liability", subtype="credit_card"),
        "hotel": make_account(name="Hotel", kind="liability", subtype="credit_card"),
    }
    sapphire = db_session.get(Account, ids["sapphire"])
    assert sapphire is not None
    sapphire.annual_fee = Decimal("95.00")

    def perk(account: str, name: str, amount: str, cadence: PerkCadence, **kw: Any) -> CardPerk:
        p = CardPerk(
            account_id=ids[account],
            name=name,
            value=Decimal(amount),
            cadence=cadence,
            anchor_on=kw.pop("anchor_on", JAN),
            **kw,
        )
        db_session.add(p)
        db_session.flush()
        return p

    dining = perk("sapphire", "Dining", "15.00", PerkCadence.MONTHLY)
    perk("sapphire", "Travel", "200.00", PerkCadence.ANNUAL)
    perk("sapphire", "Retired", "99.00", PerkCadence.MONTHLY, is_active=False)
    perk("hotel", "Hotel credit", "300.00", PerkCadence.ANNUAL, anchor_on=dt.date(2025, 3, 1))
    db_session.add_all(
        [
            PerkRedemption(perk_id=dining.id, period_start=dt.date(2026, 3, 1)),
            PerkRedemption(
                perk_id=dining.id, period_start=dt.date(2026, 5, 1), amount=Decimal("10.00")
            ),
        ]
    )
    db_session.flush()
    return ids


def test_a_card_that_is_not_earning_its_fee(db_session: Session, cards: dict[str, int]) -> None:
    sapphire = next(c for c in value(db_session, 2026, TODAY) if c.account.id == cards["sapphire"])

    assert (sapphire.fee, sapphire.realised, sapphire.available) == (
        Decimal("95.00"),
        Decimal("25.00"),
        Decimal("290.00"),
    )
    assert sapphire.utilisation_bps == 862
    assert sapphire.missed_periods == 3
    assert sapphire.net == Decimal("-70.00")


def test_no_fee_recorded_is_unknown_not_free(db_session: Session, cards: dict[str, int]) -> None:
    plain = next(c for c in value(db_session, 2026, TODAY) if c.account.id == cards["plain"])

    assert plain.fee is None
    assert (plain.realised, plain.net, plain.utilisation_bps) == (
        Decimal("0.00"),
        Decimal("0.00"),
        None,
    )


def test_a_period_belongs_to_the_year_it_began_in(
    db_session: Session, cards: dict[str, int]
) -> None:
    hotel = next(c for c in value(db_session, 2026, TODAY) if c.account.id == cards["hotel"])

    assert hotel.available == Decimal("300.00")


def test_realised_agrees_with_the_cards_screen(db_session: Session, cards: dict[str, int]) -> None:
    for card in value(db_session, 2026, TODAY):
        assert card.realised == card_service.realised_this_year(db_session, card.account.id, TODAY)


def test_the_tool(db_session: Session, owner_id: int, cards: dict[str, int]) -> None:
    ctx = ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )

    data = json.loads(load_all().run("cards_value", {}, ctx).content)["data"]
    sapphire = next(c for c in data["cards"] if c["name_text"] == "Sapphire")

    assert data["year"] == 2026
    assert sapphire["net_value"].startswith("-$70.00 [")
    assert sapphire["utilisation_pct"].startswith("8.62% [")

    future = load_all().run("cards_value", {"year": 2027}, ctx)
    assert future.status is LookupStatus.INVALID_ARGS
