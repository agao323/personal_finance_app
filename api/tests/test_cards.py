"""Credit cards and perk redemption, through HTTP.

Every test names an explicit date. Nothing in this feature reads the clock, and that is
the property being relied on here — "does it roll over correctly" is not a question you
can ask a function that decides for itself what day it is.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def card_id(make_account: Callable[..., int]) -> int:
    return make_account(name="Sapphire", kind="liability", subtype="credit_card")


@pytest.fixture
def add_perk(client: TestClient) -> Callable[..., dict[str, object]]:
    def _add(
        account_id: int,
        name: str = "Airline credit",
        value_cents: int = 20_000,
        cadence: str = "annual",
        anchor_on: str = "2026-01-01",
    ) -> dict[str, object]:
        response = client.post(
            f"/cards/{account_id}/perks",
            json={
                "name": name,
                "value_cents": value_cents,
                "cadence": cadence,
                "anchor_on": anchor_on,
            },
        )
        assert response.status_code == 201, response.text
        body: dict[str, object] = response.json()
        return body

    return _add


# ── listing ───────────────────────────────────────────────────────────────────


def test_a_card_lists_its_perks_with_the_current_period(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    add_perk(card_id)

    body = client.get("/cards", params={"on": "2026-06-15"}).json()

    card = next(c for c in body if c["account_id"] == card_id)
    perk = card["perks"][0]
    assert perk["value_cents"] == 20_000
    assert perk["current_period"]["start"] == "2026-01-01"
    assert perk["current_period"]["end"] == "2027-01-01"
    assert perk["current_period"]["is_used"] is False


def test_unused_value_is_totalled_per_card(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    add_perk(card_id, name="Airline", value_cents=20_000)
    second = add_perk(card_id, name="Hotel", value_cents=5_000, cadence="quarterly")

    client.post(f"/perks/{second['id']}/redemptions", json={"on": "2026-06-15"})
    body = client.get("/cards", params={"on": "2026-06-15"}).json()

    card = next(c for c in body if c["account_id"] == card_id)
    assert card["unused_cents"] == 20_000


def test_a_perk_before_its_first_period_has_no_current_period(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """Different from having an unused one — the perk has not started."""
    add_perk(card_id, anchor_on="2027-01-01")

    body = client.get("/cards", params={"on": "2026-06-15"}).json()

    card = next(c for c in body if c["account_id"] == card_id)
    assert card["perks"][0]["current_period"] is None
    assert card["unused_cents"] == 0


# ── marking used ──────────────────────────────────────────────────────────────


def test_marking_and_unmarking(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id)

    marked = client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})
    assert marked.status_code == 200
    assert marked.json()["current_period"]["is_used"] is True

    cleared = client.request(
        "DELETE", f"/perks/{perk['id']}/redemptions", params={"on": "2026-06-15"}
    )
    assert cleared.status_code == 200
    assert cleared.json()["current_period"]["is_used"] is False


def test_marking_twice_is_not_an_error(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The button gets pressed twice. Answering 409 would be worse than the no-op."""
    perk = add_perk(card_id)

    first = client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})
    second = client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["current_period"]["is_used"] is True


def test_unmarking_something_never_marked_is_a_no_op(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id)

    response = client.request(
        "DELETE", f"/perks/{perk['id']}/redemptions", params={"on": "2026-06-15"}
    )

    assert response.status_code == 200
    assert response.json()["current_period"]["is_used"] is False


def test_a_mark_belongs_to_one_period_only(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The rollover. Marking December must not carry into January.

    A monthly perk marked on 31 December is spent for December and available again on
    1 January — the single most important behaviour in the feature, and the one that
    would be invisible for a month if it were wrong.
    """
    perk = add_perk(card_id, cadence="monthly")

    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-12-31"})

    december = client.get("/cards", params={"on": "2026-12-31"}).json()
    january = client.get("/cards", params={"on": "2027-01-01"}).json()

    assert december[0]["perks"][0]["current_period"]["is_used"] is True
    assert january[0]["perks"][0]["current_period"]["is_used"] is False


def test_marking_before_the_first_period_is_refused(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id, anchor_on="2027-01-01")

    response = client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    assert response.status_code == 422


# ── upcoming ──────────────────────────────────────────────────────────────────


def test_upcoming_orders_by_soonest_then_by_value(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    # Monthly ends 30 June (15 days away); annual ends 31 December.
    add_perk(card_id, name="Monthly dining", value_cents=2_500, cadence="monthly")
    add_perk(card_id, name="Airline", value_cents=20_000, cadence="annual")
    # Same end date as the monthly one, smaller — should come second.
    add_perk(card_id, name="Monthly rideshare", value_cents=1_500, cadence="monthly")

    body = client.get("/perks/upcoming", params={"on": "2026-06-15", "within_days": 30}).json()

    assert [p["perk"]["name"] for p in body["perks"]] == ["Monthly dining", "Monthly rideshare"]
    assert body["total_cents"] == 4_000


def test_upcoming_excludes_what_is_already_used(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id, cadence="monthly")
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    body = client.get("/perks/upcoming", params={"on": "2026-06-15"}).json()

    assert body["perks"] == []
    assert body["total_cents"] == 0


def test_upcoming_excludes_retired_perks_and_closed_cards(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    add_perk: Callable[..., dict[str, object]],
) -> None:
    """A perk on a card you no longer hold is not something you can still use."""
    open_card = make_account(name="Open", kind="liability", subtype="credit_card")
    closed = make_account(
        name="Closed", kind="liability", subtype="credit_card", closed_at=dt.date(2026, 3, 1)
    )
    retired = add_perk(open_card, name="Retired", cadence="monthly")
    add_perk(closed, name="On a closed card", cadence="monthly")
    client.patch(f"/perks/{retired['id']}", json={"is_active": False})

    body = client.get("/perks/upcoming", params={"on": "2026-06-15"}).json()

    assert body["perks"] == []


def test_upcoming_respects_the_window(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    add_perk(card_id, name="Airline", cadence="annual")

    near = client.get("/perks/upcoming", params={"on": "2026-06-15", "within_days": 30}).json()
    far = client.get("/perks/upcoming", params={"on": "2026-06-15", "within_days": 366}).json()

    assert near["perks"] == []
    assert [p["perk"]["name"] for p in far["perks"]] == ["Airline"]


# ── refusals and editing ──────────────────────────────────────────────────────


def test_a_perk_cannot_be_attached_to_something_that_is_not_a_card(
    client: TestClient, make_account: Callable[..., int], add_perk: Callable[..., dict[str, object]]
) -> None:
    mortgage = make_account(name="Mortgage", kind="liability", subtype="mortgage")

    response = client.post(
        f"/cards/{mortgage}/perks",
        json={"name": "Nope", "value_cents": 100, "cadence": "annual", "anchor_on": "2026-01-01"},
    )

    assert response.status_code == 404


def test_editing_the_value_keeps_it_a_decimal(
    client: TestClient,
    db_session: Session,
    card_id: int,
    add_perk: Callable[..., dict[str, object]],
) -> None:
    """Cents on the wire, Decimal in the column. The conversion is easy to skip."""
    perk = add_perk(card_id, value_cents=20_000)

    updated = client.patch(f"/perks/{perk['id']}", json={"value_cents": 12_345})

    assert updated.json()["value_cents"] == 12_345
    stored = db_session.execute(
        text("SELECT value FROM card_perks WHERE id = :i"), {"i": perk["id"]}
    ).scalar_one()
    assert str(stored) == "123.45"


def test_retiring_a_perk_keeps_its_history(
    client: TestClient,
    db_session: Session,
    card_id: int,
    add_perk: Callable[..., dict[str, object]],
) -> None:
    perk = add_perk(card_id)
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    client.patch(f"/perks/{perk['id']}", json={"is_active": False})

    remaining = db_session.execute(
        text("SELECT count(*) FROM perk_redemptions WHERE perk_id = :i"), {"i": perk["id"]}
    ).scalar_one()
    assert remaining == 1
