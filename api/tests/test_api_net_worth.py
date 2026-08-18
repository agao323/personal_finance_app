"""Functional tests for the net worth endpoints.

These go through HTTP and the response models, so they catch what the service tests
cannot: a field renamed in a schema, a query parameter alias that does not match the
frozen contract, cents conversion, and the view parameter actually reaching the
calculation.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.balances import record_balance
from app.services.ownership import create_initial_stake, transition_stake

JAN = dt.date(2026, 1, 1)
MAR = dt.date(2026, 3, 1)
JUN = dt.date(2026, 6, 1)


# ── GET /net-worth ────────────────────────────────────────────────────────────


def test_current_net_worth(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("1234.56"))

    body = client.get("/net-worth", params={"as_of": "2026-03-01"}).json()

    # Integer cents on the wire, never a float or a decimal string.
    assert body["net_worth_cents"] == 123456
    assert body["assets_cents"] == 123456
    assert body["liabilities_cents"] == 0
    assert body["as_of"] == "2026-03-01"
    assert body["view"] == "mine"


def test_breakdown_by_kind(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    cash = make_account(name="Checking")
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    for account_id in (cash, card):
        create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, cash, JAN, Decimal("5000.00"))
    record_balance(db_session, card, JAN, Decimal("1500.00"))

    body = client.get("/net-worth", params={"as_of": "2026-03-01"}).json()

    kinds = {row["kind"]: row["total_cents"] for row in body["breakdown"]}
    assert kinds == {"liquid_asset": 500000, "liability": 150000}
    assert body["net_worth_cents"] == 350000
    # Liabilities are reported positive; net worth has already subtracted them.
    assert body["liabilities_cents"] == 150000


def test_view_household_sums_every_stake(
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

    mine = client.get("/net-worth", params={"as_of": "2026-03-01", "view": "mine"}).json()
    household = client.get("/net-worth", params={"as_of": "2026-03-01", "view": "household"}).json()

    assert mine["net_worth_cents"] == 600000
    assert household["net_worth_cents"] == 1000000
    assert household["view"] == "household"


def test_empty_database_is_zero_not_an_error(client: TestClient) -> None:
    response = client.get("/net-worth")

    assert response.status_code == 200
    assert response.json()["net_worth_cents"] == 0


def test_stale_accounts_are_named(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    fresh = client.get("/net-worth", params={"as_of": "2026-03-01"}).json()
    stale = client.get("/net-worth", params={"as_of": "2027-01-01"}).json()

    assert fresh["stale_account_ids"] == []
    # Still counted, but reported — dropping it would make net worth silently fall.
    assert stale["stale_account_ids"] == [account_id]
    assert stale["net_worth_cents"] == 100000


def test_rejects_a_malformed_date(client: TestClient) -> None:
    assert client.get("/net-worth", params={"as_of": "not-a-date"}).status_code == 422


# ── GET /net-worth/series ─────────────────────────────────────────────────────


def test_series_over_a_range(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))
    record_balance(db_session, account_id, MAR, Decimal("3000.00"))

    body = client.get(
        "/net-worth/series",
        params={"from": "2026-01-01", "to": "2026-04-01", "interval": "month"},
    ).json()

    values = {p["as_of"]: p["net_worth_cents"] for p in body["points"]}
    assert values["2026-01-01"] == 100000
    # February carries January forward — nobody records every account every day.
    assert values["2026-02-01"] == 100000
    assert values["2026-03-01"] == 300000
    assert body["interval"] == "month"


def test_series_uses_each_points_own_stake(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """A stake change in June must not rewrite March."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("2000.00"))
    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    body = client.get("/net-worth/series", params={"from": "2026-01-01", "to": "2026-08-01"}).json()

    values = {p["as_of"]: p["net_worth_cents"] for p in body["points"]}
    assert values["2026-03-01"] == 200000
    assert values["2026-07-01"] == 100000


def test_series_drops_a_closed_account_partway_through(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    car = make_account(name="Car", kind="illiquid_asset", subtype="vehicle", closed_at=JUN)
    create_initial_stake(db_session, car, owner_id, JAN)
    record_balance(db_session, car, JAN, Decimal("15000.00"))

    body = client.get("/net-worth/series", params={"from": "2026-01-01", "to": "2026-08-01"}).json()

    values = {p["as_of"]: p["net_worth_cents"] for p in body["points"]}
    assert values["2026-03-01"] == 1500000
    assert values["2026-07-01"] == 0


def test_series_starts_at_the_first_snapshot_not_the_requested_start(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """A chart starting at zero would show a fortune appearing overnight."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, MAR)
    record_balance(db_session, account_id, MAR, Decimal("5000.00"))

    body = client.get("/net-worth/series", params={"from": "2025-01-01", "to": "2026-04-01"}).json()

    assert body["points"][0]["as_of"] == "2026-03-01"


def test_empty_history_returns_no_points(client: TestClient) -> None:
    body = client.get("/net-worth/series").json()

    assert body["points"] == []


def test_single_snapshot_returns_a_usable_series(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """Day one, before any history import. Must not be an error."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, MAR)
    record_balance(db_session, account_id, MAR, Decimal("500.00"))

    body = client.get(
        "/net-worth/series",
        params={"from": "2026-03-01", "to": "2026-03-01", "interval": "month"},
    ).json()

    assert len(body["points"]) == 1
    assert body["points"][0]["net_worth_cents"] == 50000


def test_series_reports_stale_points(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """The signal ticket 027 asked for.

    Without it a flat stretch drawn from a year-old balance looks identical to a
    measured one, and on a sparse history that is most of the line.
    """
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    body = client.get("/net-worth/series", params={"from": "2026-01-01", "to": "2027-01-01"}).json()

    points = {p["as_of"]: p["stale_account_count"] for p in body["points"]}
    assert points["2026-02-01"] == 0
    assert points["2026-12-01"] == 1


def test_series_honours_the_view(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    account_id = make_account(name="Joint")
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))
    create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("50"))
    record_balance(db_session, account_id, JAN, Decimal("8000.00"))

    mine = client.get("/net-worth/series", params={"from": "2026-01-01", "to": "2026-02-01"}).json()
    household = client.get(
        "/net-worth/series",
        params={"from": "2026-01-01", "to": "2026-02-01", "view": "household"},
    ).json()

    assert mine["points"][0]["net_worth_cents"] == 400000
    assert household["points"][0]["net_worth_cents"] == 800000


def test_series_always_includes_the_requested_end(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """Otherwise the chart's last value silently predates the range asked for."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    body = client.get(
        "/net-worth/series",
        params={"from": "2026-01-01", "to": "2026-03-15", "interval": "month"},
    ).json()

    assert body["points"][-1]["as_of"] == "2026-03-15"


def test_daily_interval(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("100.00"))

    body = client.get(
        "/net-worth/series",
        params={"from": "2026-01-01", "to": "2026-01-05", "interval": "day"},
    ).json()

    assert [p["as_of"] for p in body["points"]] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
        "2026-01-05",
    ]


def test_weekly_interval(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("100.00"))

    body = client.get(
        "/net-worth/series",
        params={"from": "2026-01-01", "to": "2026-01-22", "interval": "week"},
    ).json()

    assert [p["as_of"] for p in body["points"]] == [
        "2026-01-01",
        "2026-01-08",
        "2026-01-15",
        "2026-01-22",
    ]


def test_range_entirely_before_any_history_returns_no_points(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """Asking for 2024 when the first balance is 2026 is an empty answer, not a zero."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    record_balance(db_session, account_id, JAN, Decimal("100.00"))

    body = client.get("/net-worth/series", params={"from": "2024-01-01", "to": "2024-06-01"}).json()

    assert body["points"] == []
