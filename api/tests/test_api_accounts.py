"""Functional tests for the accounts API.

The invariant worth most attention is that creating an account writes its stake in the
same transaction. An account with no stake row contributes to no net worth figure — it
exists and is simultaneously invisible, which is the worst failure mode available here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.balances import record_balance
from app.services.ownership import create_initial_stake

JAN = dt.date(2026, 1, 1)
JUN = dt.date(2026, 6, 1)


# ── creation ──────────────────────────────────────────────────────────────────


def test_creating_an_account_writes_its_stake(client: TestClient, db_session: Session) -> None:
    """The invariant the whole ownership design rests on."""
    response = client.post(
        "/accounts",
        json={"name": "New savings", "kind": "liquid_asset", "subtype": "savings"},
    )

    assert response.status_code == 201
    account_id = response.json()["id"]

    stakes = (
        db_session.execute(
            text("SELECT percentage FROM ownership_stakes WHERE account_id = :a"),
            {"a": account_id},
        )
        .scalars()
        .all()
    )

    assert stakes == [Decimal("100.00")]


def test_creating_with_an_opening_balance(client: TestClient) -> None:
    body = client.post(
        "/accounts",
        json={
            "name": "Brokerage",
            "kind": "liquid_asset",
            "subtype": "brokerage",
            "opening_balance_cents": 2_500_000,
            "opening_balance_as_of": "2026-01-01",
        },
    ).json()

    assert body["balance_cents"] == 2_500_000


def test_creating_with_a_partial_stake(client: TestClient) -> None:
    """A 50%-owned rental: 5000 bps in, both values out."""
    body = client.post(
        "/accounts",
        json={
            "name": "Rental",
            "kind": "illiquid_asset",
            "subtype": "real_estate",
            "ownership_percentage_bps": 5000,
            "opening_balance_cents": 40_000_000,
            "opening_balance_as_of": "2026-01-01",
        },
    ).json()

    assert body["balance_cents"] == 40_000_000  # raw
    assert body["adjusted_balance_cents"] == 20_000_000  # your share
    assert body["current_stake_bps"] == 5000


def test_institution_is_created_or_reused_by_name(client: TestClient, db_session: Session) -> None:
    """Importing twice must not spawn duplicate institutions."""
    for name in ("A", "B"):
        client.post(
            "/accounts",
            json={
                "name": name,
                "kind": "liquid_asset",
                "subtype": "checking",
                "institution_name": "Shared Bank",
            },
        )

    count = db_session.execute(
        text("SELECT count(*) FROM institutions WHERE name = 'Shared Bank'")
    ).scalar_one()
    assert count == 1


def test_rejects_an_unknown_kind(client: TestClient) -> None:
    response = client.post("/accounts", json={"name": "X", "kind": "crypto", "subtype": "checking"})
    assert response.status_code == 422


def test_rejects_an_empty_name(client: TestClient) -> None:
    response = client.post(
        "/accounts", json={"name": "", "kind": "liquid_asset", "subtype": "checking"}
    )
    assert response.status_code == 422


# ── listing ───────────────────────────────────────────────────────────────────


def test_list_exposes_raw_and_adjusted(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The distinction that makes this app different from an off-the-shelf one."""
    account_id = make_account(name="Rental", kind="illiquid_asset", subtype="real_estate")
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))
    record_balance(db_session, account_id, JAN, Decimal("400000.00"))

    body = client.get("/accounts").json()
    account = body["groups"][0]["accounts"][0]

    assert account["balance_cents"] == 40_000_000
    assert account["adjusted_balance_cents"] == 20_000_000
    assert body["total_cents"] == 40_000_000
    assert body["adjusted_total_cents"] == 20_000_000


def test_list_groups_by_kind_with_subtotals(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    cash = make_account(name="Checking")
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    for account_id in (cash, card):
        create_initial_stake(db_session, account_id, owner_id, JAN)
        record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    groups = {g["kind"]: g for g in client.get("/accounts").json()["groups"]}

    assert groups["liquid_asset"]["total_cents"] == 100_000
    assert groups["liability"]["total_cents"] == 100_000


def test_closed_accounts_are_hidden_but_requestable(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The history is still real; an accounts screen that forgets a paid-off loan confuses."""
    account_id = make_account(name="Old car", closed_at=JAN)
    create_initial_stake(db_session, account_id, owner_id, dt.date(2025, 1, 1))
    record_balance(db_session, account_id, dt.date(2025, 1, 1), Decimal("9000.00"))

    assert client.get("/accounts").json()["groups"] == []
    assert client.get("/accounts", params={"include_closed": True}).json()["groups"]


def test_list_honours_the_view(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    account_id = make_account(name="Joint")
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))
    create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("40"))
    record_balance(db_session, account_id, JAN, Decimal("10000.00"))

    mine = client.get("/accounts").json()
    household = client.get("/accounts", params={"view": "household"}).json()

    assert mine["adjusted_total_cents"] == 600_000
    assert household["adjusted_total_cents"] == 1_000_000


def test_list_surfaces_staleness(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """So the UI can prompt an update rather than presenting an old number as current."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, dt.date(2020, 1, 1))
    record_balance(db_session, account_id, dt.date(2020, 1, 1), Decimal("100.00"))

    account = client.get("/accounts").json()["groups"][0]["accounts"][0]

    assert account["is_stale"] is True
    assert account["balance_as_of"] == "2020-01-01"


# ── detail and history ────────────────────────────────────────────────────────


def test_detail_includes_stake_history_with_dates(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Showing the dates is what makes effective-dating visible as a feature."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    client.post(
        f"/accounts/{account_id}/stakes",
        json={"owner_user_id": owner_id, "percentage_bps": 5000, "effective_from": "2026-06-01"},
    )

    stakes = client.get(f"/accounts/{account_id}").json()["stakes"]

    assert len(stakes) == 2
    assert stakes[0]["effective_to"] == "2026-06-01"
    assert stakes[1]["effective_to"] is None
    assert stakes[0]["owner_display_name"]


def test_history_returns_the_snapshot_series(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("100.00"))
    record_balance(db_session, account_id, JUN, Decimal("300.00"))

    points = client.get(f"/accounts/{account_id}/history").json()["points"]

    assert [p["balance_cents"] for p in points] == [10_000, 30_000]


def test_unknown_account_is_a_404(client: TestClient) -> None:
    assert client.get("/accounts/999999").status_code == 404
    assert client.get("/accounts/999999/history").status_code == 404


# ── writes ────────────────────────────────────────────────────────────────────


def test_recording_a_balance(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    response = client.post(
        f"/accounts/{account_id}/balances",
        json={"as_of": "2026-03-01", "balance_cents": 123_456},
    )

    assert response.status_code == 201
    assert response.json()["balance_cents"] == 123_456


def test_recording_the_same_date_twice_replaces(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Correcting a typo is one call, not a duplicate row."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    for cents in (100_000, 125_000):
        client.post(
            f"/accounts/{account_id}/balances",
            json={"as_of": "2026-03-01", "balance_cents": cents},
        )

    points = client.get(f"/accounts/{account_id}/history").json()["points"]
    assert len(points) == 1
    assert points[0]["balance_cents"] == 125_000


def test_stake_transition_does_not_rewrite_history(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Halving a stake in June must leave March reading 100%."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("2000.00"))

    client.post(
        f"/accounts/{account_id}/stakes",
        json={"owner_user_id": owner_id, "percentage_bps": 5000, "effective_from": "2026-06-01"},
    )

    march = client.get("/net-worth", params={"as_of": "2026-03-01"}).json()
    september = client.get("/net-worth", params={"as_of": "2026-09-01"}).json()

    assert march["net_worth_cents"] == 200_000
    assert september["net_worth_cents"] == 100_000


def test_a_stake_over_100_percent_is_rejected(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("70"))

    response = client.post(
        f"/accounts/{account_id}/stakes",
        json={"owner_user_id": partner_id, "percentage_bps": 5000, "effective_from": "2026-01-01"},
    )

    assert response.status_code == 422
    assert "over 100" in response.json()["detail"]


def test_closing_an_account_via_patch(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Closing is a date, not a deletion — the history stays."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("500.00"))

    client.patch(f"/accounts/{account_id}", json={"closed_at": "2026-06-01"})

    assert client.get("/accounts").json()["groups"] == []
    assert client.get(f"/accounts/{account_id}/history").json()["points"]


def test_renaming_an_account(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account(name="Old name")
    create_initial_stake(db_session, account_id, owner_id, JAN)

    body = client.patch(f"/accounts/{account_id}", json={"name": "New name"}).json()

    assert body["name"] == "New name"


def test_rejects_a_bps_value_over_10000(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    account_id = make_account()

    response = client.post(
        f"/accounts/{account_id}/stakes",
        json={"owner_user_id": 1, "percentage_bps": 10_001, "effective_from": "2026-01-01"},
    )

    assert response.status_code == 422


# ── the annual fee (062) ──────────────────────────────────────────────────────


def test_setting_and_clearing_an_annual_fee(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """Clearing means null, not zero.

    A card with no fee recorded shows no net-value panel; a card whose fee is $0 is a
    different and rarer claim. Conflating them makes "not filled in" indistinguishable
    from "free".
    """
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")

    client.patch(
        f"/accounts/{card}", json={"annual_fee_cents": 69_500, "fee_renews_on": "2026-03-01"}
    )
    stored = db_session.execute(
        text("SELECT annual_fee, fee_renews_on FROM accounts WHERE id = :i"), {"i": card}
    ).one()
    assert str(stored[0]) == "695.00"
    assert stored[1] == dt.date(2026, 3, 1)

    client.patch(f"/accounts/{card}", json={"annual_fee_cents": None, "fee_renews_on": None})
    cleared = db_session.execute(
        text("SELECT annual_fee FROM accounts WHERE id = :i"), {"i": card}
    ).scalar_one()
    assert cleared is None


def test_a_fee_reaches_the_card_screen_as_cents(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")
    client.patch(
        f"/accounts/{card}", json={"annual_fee_cents": 69_500, "fee_renews_on": "2026-03-01"}
    )

    body = client.get("/cards", params={"on": "2026-06-15"}).json()

    assert next(c for c in body if c["account_id"] == card)["annual_fee_cents"] == 69_500


# ── removing an account (063) ─────────────────────────────────────────────────


def test_the_deletion_preview_counts_what_would_be_destroyed(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    owner_id: int,
) -> None:
    """Counted from the database, not estimated.

    A warning with a wrong number is worse than a vague one — it teaches you the numbers
    are decorative.
    """
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, card, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, card, dt.date(2026, 1, 1), Decimal("1200.00"))
    record_balance(db_session, card, dt.date(2026, 2, 1), Decimal("900.00"))
    make_transaction(card, dt.date(2026, 1, 15), "-50.00")
    perk = db_session.execute(
        text(
            "INSERT INTO card_perks (account_id, name, value, cadence, anchor_on) "
            "VALUES (:a, 'Travel', 200.00, 'annual', '2026-01-01') RETURNING id"
        ),
        {"a": card},
    ).scalar_one()
    db_session.execute(
        text("INSERT INTO perk_redemptions (perk_id, period_start) VALUES (:p, '2026-01-01')"),
        {"p": perk},
    )
    db_session.flush()

    body = client.get(f"/accounts/{card}/deletion-preview").json()

    assert body["balance_snapshots"] == 2
    assert body["transactions"] == 1
    assert body["ownership_stakes"] == 1
    assert body["card_perks"] == 1
    assert body["perk_redemptions"] == 1
    assert body["earliest_snapshot"] == "2026-01-01"


def test_deleting_requires_naming_the_account(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    """A destructive action reachable by one mis-click happens by mis-click.

    Checked server-side, not only in a dialog — a guard living in one component is a guard
    a second caller does not have.
    """
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")

    wrong = client.request("DELETE", f"/accounts/{card}", json={"confirm_name": "platinum"})

    assert wrong.status_code == 400
    assert "Platinum" in wrong.json()["detail"]
    assert client.get(f"/accounts/{card}").status_code == 200, "still there"


def test_deleting_cascades_to_every_child(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    owner_id: int,
) -> None:
    """The cascade is the whole risk, so it is asserted rather than assumed."""
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, card, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, card, dt.date(2026, 1, 1), Decimal("1200.00"))
    make_transaction(card, dt.date(2026, 1, 15), "-50.00")
    db_session.flush()

    response = client.request("DELETE", f"/accounts/{card}", json={"confirm_name": "Platinum"})

    assert response.status_code == 204
    for table in ("balance_snapshots", "transactions", "ownership_stakes"):
        remaining = db_session.execute(
            text(f"SELECT count(*) FROM {table} WHERE account_id = :a"), {"a": card}
        ).scalar_one()
        assert remaining == 0, table


def test_closing_an_account_keeps_everything(
    client: TestClient, db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The alternative the dialog offers first, and what most people actually want."""
    card = make_account(name="Platinum", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, card, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, card, dt.date(2026, 1, 1), Decimal("1200.00"))
    db_session.flush()

    client.patch(f"/accounts/{card}", json={"closed_at": "2026-06-01"})

    kept = db_session.execute(
        text("SELECT count(*) FROM balance_snapshots WHERE account_id = :a"), {"a": card}
    ).scalar_one()
    assert kept == 1
