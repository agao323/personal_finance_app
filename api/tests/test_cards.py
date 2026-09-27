"""Credit cards and perk redemption, through HTTP.

Every test names an explicit date. Nothing in this feature reads the clock, and that is
the property being relied on here — "does it roll over correctly" is not a question you
can ask a function that decides for itself what day it is.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

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


# ── deleting versus retiring (054) ────────────────────────────────────────────


def test_an_unused_perk_can_be_deleted(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The perk you added by mistake."""
    perk = add_perk(card_id)

    assert client.delete(f"/perks/{perk['id']}").status_code == 204
    assert client.get("/cards", params={"on": "2026-06-15"}).json()[0]["perks"] == []


def test_a_used_perk_is_refused_and_told_to_retire(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """Deleting it would erase what you actually used.

    Two actions that look alike: delete is for a mistake, retire is for a perk the card
    stopped offering. The refusal names the alternative rather than just saying no.
    """
    perk = add_perk(card_id)
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    response = client.delete(f"/perks/{perk['id']}")

    assert response.status_code == 409
    assert "retire" in response.json()["detail"].lower()

    # And retiring works, keeping the redemption.
    assert client.patch(f"/perks/{perk['id']}", json={"is_active": False}).status_code == 200
    assert client.get(f"/perks/{perk['id']}/history").json()["redemptions"] != []


# ── partial amounts (054) ─────────────────────────────────────────────────────


def test_a_partial_amount_round_trips_as_cents(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id, value_cents=20_000)

    body = client.post(
        f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15", "amount_cents": 5_000}
    ).json()

    assert body["current_period"]["is_used"] is True
    assert body["current_period"]["used_amount_cents"] == 5_000


def test_omitting_the_amount_means_full_face_value(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """What one tap records. `None`, not the perk's value copied in."""
    perk = add_perk(card_id, value_cents=20_000)

    body = client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"}).json()

    assert body["current_period"]["is_used"] is True
    assert body["current_period"]["used_amount_cents"] is None
    # History resolves it to the face value and says where the number came from.
    entry = client.get(f"/perks/{perk['id']}/history").json()["redemptions"][0]
    assert (entry["realised_cents"], entry["is_face_value"]) == (20_000, True)


def test_re_marking_updates_the_amount_rather_than_erroring(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """Correcting "I used all of it" to "I used $50 of it" is a re-mark, not a conflict."""
    perk = add_perk(card_id, value_cents=20_000)

    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})
    second = client.post(
        f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15", "amount_cents": 5_000}
    )

    assert second.status_code == 200
    assert second.json()["current_period"]["used_amount_cents"] == 5_000


# ── urgency, reported not recomputed (054) ────────────────────────────────────


def test_urgency_comes_from_the_service_and_varies_by_cadence(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The same days-remaining means different things at different cadences.

    The browser reads this flag rather than computing a threshold, so the rule lives in
    exactly one place.
    """
    add_perk(card_id, name="Monthly", cadence="monthly", anchor_on="2026-01-01")
    add_perk(card_id, name="Annual", cadence="annual", anchor_on="2026-01-01")

    def perks_on(day: str) -> dict[str, Any]:
        return {p["name"]: p for p in client.get("/cards", params={"on": day}).json()[0]["perks"]}

    # 28 June: the monthly period ends 1 July, so 2 days left — inside monthly's 7-day
    # threshold. The annual period ends 1 Jan 2027, far outside its 30.
    late = perks_on("2026-06-28")
    assert late["Monthly"]["current_period"]["is_urgent"] is True
    assert late["Annual"]["current_period"]["is_urgent"] is False

    # 10 June: 20 days left on the monthly one, and it is calm. A single 30-day window
    # would have called this urgent, which is the complaint the cadence table answers.
    mid = perks_on("2026-06-10")
    assert mid["Monthly"]["current_period"]["is_urgent"] is False

    # 20 December: 11 days left on the annual one, now urgent.
    assert perks_on("2026-12-20")["Annual"]["current_period"]["is_urgent"] is True


def test_upcoming_reports_an_urgent_subtotal(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    add_perk(card_id, name="Monthly", value_cents=2_500, cadence="monthly")
    add_perk(card_id, name="Annual", value_cents=20_000, cadence="annual")

    body = client.get("/perks/upcoming", params={"on": "2026-06-28", "within_days": 366}).json()

    assert body["total_cents"] == 22_500
    # Only the monthly one is close to its own boundary.
    assert body["urgent_cents"] == 2_500


def test_upcoming_defaults_to_ninety_days(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """45 hid annual credits entirely, which was the original complaint."""
    body = client.get("/perks/upcoming", params={"on": "2026-06-15"}).json()

    assert body["within_days"] == 90


# ── history (054) ─────────────────────────────────────────────────────────────


def test_wallet_history_spans_every_card_newest_first(
    client: TestClient,
    make_account: Callable[..., int],
    add_perk: Callable[..., dict[str, object]],
) -> None:
    one = make_account(name="Card one", kind="liability", subtype="credit_card")
    two = make_account(name="Card two", kind="liability", subtype="credit_card")
    first = add_perk(one, name="Monthly one", cadence="monthly")
    second = add_perk(two, name="Monthly two", cadence="monthly")

    client.post(f"/perks/{first['id']}/redemptions", json={"on": "2026-03-10"})
    client.post(f"/perks/{second['id']}/redemptions", json={"on": "2026-06-10"})

    body = client.get("/cards/history", params={"on": "2026-06-15"}).json()

    assert [r["card_name"] for r in body["redemptions"]] == ["Card two", "Card one"]
    assert body["from_date"] is None, "no default cut-off — everything is the request"


def test_history_windowing(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    perk = add_perk(card_id, cadence="monthly")
    for day in ("2026-02-10", "2026-04-10", "2026-06-10"):
        client.post(f"/perks/{perk['id']}/redemptions", json={"on": day})

    body = client.get(
        "/cards/history", params={"from": "2026-04-01", "to": "2026-06-30", "on": "2026-06-15"}
    ).json()

    assert [r["period_start"] for r in body["redemptions"]] == ["2026-06-01", "2026-04-01"]


def test_history_counts_periods_that_closed_unused(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The number that changes behaviour.

    A monthly perk anchored 1 January, one use in March, evaluated mid-June: January,
    February, April and May closed with nothing against them. June has not closed and is
    still spendable, so it is not missed.
    """
    perk = add_perk(card_id, cadence="monthly", anchor_on="2026-01-01")
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-03-10"})

    body = client.get("/cards/history", params={"on": "2026-06-15"}).json()

    assert body["missed_periods"] == 4


def test_a_perks_own_history_is_scoped_to_it(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    one = add_perk(card_id, name="One", cadence="monthly")
    two = add_perk(card_id, name="Two", cadence="monthly")
    client.post(f"/perks/{one['id']}/redemptions", json={"on": "2026-06-10"})
    client.post(f"/perks/{two['id']}/redemptions", json={"on": "2026-06-10"})

    body = client.get(f"/perks/{one['id']}/history", params={"on": "2026-06-15"}).json()

    assert [r["perk_name"] for r in body["redemptions"]] == ["One"]


# ── the card row's figures (054) ──────────────────────────────────────────────


def test_a_card_reports_its_fee_and_what_it_realised(
    client: TestClient,
    db_session: Session,
    card_id: int,
    add_perk: Callable[..., dict[str, object]],
) -> None:
    """Net card value. Realised counts redemptions, never what was merely available."""
    db_session.execute(
        text("UPDATE accounts SET annual_fee = 695.00, fee_renews_on = '2026-03-01' WHERE id = :i"),
        {"i": card_id},
    )
    perk = add_perk(card_id, value_cents=20_000, anchor_on="2026-01-01")
    client.post(
        f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15", "amount_cents": 7_500}
    )

    card = client.get("/cards", params={"on": "2026-06-15"}).json()[0]

    assert card["annual_fee_cents"] == 69_500
    assert card["fee_year_start"] == "2026-03-01"
    assert card["realised_this_fee_year_cents"] == 7_500


def test_a_card_with_no_fee_reports_none_not_zero(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """Absent is not zero — a card with no fee recorded must not claim its fee is $0."""
    add_perk(card_id)

    card = client.get("/cards", params={"on": "2026-06-15"}).json()[0]

    assert card["annual_fee_cents"] is None
    assert card["realised_this_fee_year_cents"] is None


def test_renaming_a_card_works(client: TestClient, card_id: int) -> None:
    """Asserted here so the page rebuild does not discover it missing."""
    assert client.patch(f"/accounts/{card_id}", json={"name": "Platinum"}).status_code == 200
    assert client.get("/cards", params={"on": "2026-06-15"}).json()[0]["name"] == "Platinum"


# ── a perk's recent periods ───────────────────────────────────────────────────


def test_periods_report_exactly_the_recorded_ones_as_used(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """The grid's whole job: which windows have a row, and which do not."""
    perk = add_perk(card_id, cadence="quarterly", anchor_on="2026-01-01")

    # Q1 in full, Q3 partially. Q2 and Q4 untouched.
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-02-01"})
    client.post(
        f"/perks/{perk['id']}/redemptions", json={"on": "2026-08-01", "amount_cents": 2_500}
    )

    body = client.get(f"/perks/{perk['id']}/periods", params={"back": 8, "on": "2026-10-15"}).json()

    assert body["cadence"] == "quarterly"
    assert [p["start"] for p in body["periods"]] == [
        "2026-01-01",
        "2026-04-01",
        "2026-07-01",
        "2026-10-01",
    ]
    assert [p["is_used"] for p in body["periods"]] == [True, False, True, False]
    assert [p["used_amount_cents"] for p in body["periods"]] == [None, None, 2_500, None]
    # Exactly one current period, and it is the last.
    assert [p["is_current"] for p in body["periods"]] == [False, False, False, True]


def test_has_earlier_is_false_only_at_the_start_of_history(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """A row of chips looks identical at the beginning of history and in the middle."""
    perk = add_perk(card_id, cadence="quarterly", anchor_on="2026-01-01")

    whole = client.get(f"/perks/{perk['id']}/periods", params={"back": 8, "on": "2026-10-15"})
    assert whole.json()["has_earlier"] is False

    windowed = client.get(f"/perks/{perk['id']}/periods", params={"back": 2, "on": "2026-10-15"})
    assert windowed.json()["has_earlier"] is True
    assert [p["start"] for p in windowed.json()["periods"]] == ["2026-07-01", "2026-10-01"]


def test_periods_before_a_perk_starts_are_not_offered(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """Nothing to mark, rather than a window that never happened."""
    perk = add_perk(card_id, cadence="monthly", anchor_on="2026-06-01")

    body = client.get(f"/perks/{perk['id']}/periods", params={"on": "2026-05-31"}).json()

    assert body["periods"] == []
    assert body["has_earlier"] is False


def test_a_chips_own_start_date_marks_that_period(
    client: TestClient, card_id: int, add_perk: Callable[..., dict[str, object]]
) -> None:
    """How the grid writes: the period's start is a date inside it, so it resolves to it.

    Asserted here because it is the contract between the grid and `mark_used`, and it holds
    for a month-end anchor only because periods step from the anchor.
    """
    perk = add_perk(card_id, cadence="monthly", anchor_on="2026-01-31")

    listed = client.get(f"/perks/{perk['id']}/periods", params={"on": "2026-04-15"}).json()
    second = listed["periods"][1]
    assert second["start"] == "2026-02-28"

    client.post(f"/perks/{perk['id']}/redemptions", json={"on": second["start"]})
    again = client.get(f"/perks/{perk['id']}/periods", params={"on": "2026-04-15"}).json()

    # Three periods, not four: anchored on the 31st, period 1 runs 28 February to
    # 31 March, so 15 April is only the third.
    assert [p["is_used"] for p in again["periods"]] == [False, True, False]


def test_periods_of_an_unknown_perk_is_a_404(client: TestClient) -> None:
    assert client.get("/perks/9999/periods").status_code == 404
