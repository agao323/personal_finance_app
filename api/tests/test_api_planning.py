"""The planning profile and assumptions: defaults, append-only versions, the mix, whose profile.

The migration's round trip is `test_schema.test_upgrade_downgrade_upgrade_is_clean`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import app
from app.models.enums import RiskTolerance
from app.models.planning import PlanningAssumptions

PARTNER = "partner@example.invalid"


@pytest.fixture
def as_partner(monkeypatch: pytest.MonkeyPatch, partner_id: int) -> Iterator[Callable[[], None]]:
    def switch() -> None:
        monkeypatch.setenv("DEV_IDENTITY_EMAIL", PARTNER)
        get_settings.cache_clear()

    yield switch
    get_settings.cache_clear()


def _version(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "expected_real_return_bps": 450,
        "inflation_bps": 300,
        "withdrawal_low_bps": 325,
        "withdrawal_high_bps": 400,
        "pre65_healthcare_annual_cents": 1_800_000,
        "tax_deferred_withdrawal_tax_bps": 1200,
        "risk_tolerance": "aggressive",
        "target_us_equity_bps": 5500,
        "target_intl_equity_bps": 2500,
        "target_bonds_bps": 1500,
        "target_cash_bps": 500,
        "target_other_bps": 0,
    }
    body.update(overrides)
    return body


# ── the defaults ──────────────────────────────────────────────────────────────


def test_the_migration_leaves_a_defaults_version(client: TestClient) -> None:
    (defaults,) = client.get("/planning/assumptions").json()

    assert defaults["is_default"] is True
    assert defaults["created_by_user_id"] is None
    assert (
        defaults["expected_real_return_bps"],
        defaults["inflation_bps"],
        defaults["withdrawal_low_bps"],
        defaults["withdrawal_high_bps"],
        defaults["tax_deferred_withdrawal_tax_bps"],
        defaults["risk_tolerance"],
    ) == (500, 250, 300, 450, 1500, "moderate")
    mix = [
        defaults[f"target_{k}_bps"] for k in ("us_equity", "intl_equity", "bonds", "cash", "other")
    ]
    assert mix == [4000, 2000, 3500, 500, 0] and sum(mix) == 10000
    assert defaults["pre65_healthcare_annual_cents"] is None


# ── append-only ───────────────────────────────────────────────────────────────


def test_a_new_version_is_appended_and_wins(client: TestClient, owner_id: int) -> None:
    created = client.post("/planning/assumptions", json=_version())

    assert created.status_code == 201
    history = client.get("/planning/assumptions").json()
    assert [v["is_default"] for v in history] == [False, True]
    newest = history[0]
    assert newest["id"] == created.json()["id"]
    assert newest["created_by_user_id"] == owner_id
    assert newest["pre65_healthcare_annual_cents"] == 1_800_000
    assert newest["target_us_equity_bps"] == 5500


def test_no_route_changes_or_removes_a_version(client: TestClient) -> None:
    paths = app.openapi()["paths"]

    assert set(paths["/planning/assumptions"]) == {"get", "post"}
    assert not [p for p in paths if p.startswith("/planning/assumptions/")]


# ── the mix and the bounds ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"target_cash_bps": 499}, "totals 99.99%"),
        ({"target_other_bps": 100}, "totals 101.00%"),
        ({"withdrawal_low_bps": 500, "withdrawal_high_bps": 400}, "low withdrawal rate"),
    ],
)
def test_an_inconsistent_version_is_refused(
    client: TestClient, overrides: dict[str, Any], message: str
) -> None:
    response = client.post("/planning/assumptions", json=_version(**overrides))

    assert response.status_code == 422
    assert message in str(response.json())


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_real_return_bps": 5000},
        {"inflation_bps": -2000},
        {"tax_deferred_withdrawal_tax_bps": 7000},
        {"target_bonds_bps": -100},
        {"pre65_healthcare_annual_cents": -1},
    ],
)
def test_out_of_bounds_values_are_refused(client: TestClient, overrides: dict[str, Any]) -> None:
    assert client.post("/planning/assumptions", json=_version(**overrides)).status_code == 422


def _row(**overrides: Any) -> PlanningAssumptions:
    values: dict[str, Any] = {
        "is_default": False,
        "expected_real_return_bps": 500,
        "inflation_bps": 250,
        "withdrawal_low_bps": 300,
        "withdrawal_high_bps": 450,
        "tax_deferred_withdrawal_tax_bps": 1500,
        "risk_tolerance": RiskTolerance.MODERATE,
        "target_us_equity_pct": Decimal("40"),
        "target_intl_equity_pct": Decimal("20"),
        "target_bonds_pct": Decimal("35"),
        "target_cash_pct": Decimal("5"),
        "target_other_pct": Decimal("0"),
    }
    values.update(overrides)
    return PlanningAssumptions(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_cash_pct": Decimal("4.99")},
        {"target_bonds_pct": Decimal("-5"), "target_cash_pct": Decimal("45")},
        {"withdrawal_low_bps": 500},
        {"inflation_bps": 3000},
    ],
)
def test_the_database_holds_the_same_rules(db_session: Session, overrides: dict[str, Any]) -> None:
    db_session.add(_row(**overrides))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_database_accepts_a_mix_in_hundredths(db_session: Session) -> None:
    db_session.add(
        _row(target_us_equity_pct=Decimal("33.33"), target_intl_equity_pct=Decimal("26.67"))
    )
    db_session.flush()


# ── profiles ──────────────────────────────────────────────────────────────────


def test_a_profile_starts_empty_and_is_set(client: TestClient) -> None:
    assert client.get("/planning/profile").json() == {
        "birth_year": None,
        "target_retirement_year": None,
    }

    saved = client.put(
        "/planning/profile", json={"birth_year": 1988, "target_retirement_year": 2048}
    )

    assert saved.status_code == 200
    assert client.get("/planning/profile").json() == {
        "birth_year": 1988,
        "target_retirement_year": 2048,
    }


def test_retirement_comes_after_birth(client: TestClient) -> None:
    response = client.put(
        "/planning/profile", json={"birth_year": 1988, "target_retirement_year": 1980}
    )

    assert response.status_code == 422


def test_each_member_sees_and_edits_only_their_own_profile(
    client: TestClient, as_partner: Callable[[], None]
) -> None:
    client.put("/planning/profile", json={"birth_year": 1988, "target_retirement_year": 2048})

    as_partner()
    assert client.get("/planning/profile").json()["birth_year"] is None
    client.put("/planning/profile", json={"birth_year": 1990, "target_retirement_year": 2055})
    assert client.get("/planning/profile").json()["birth_year"] == 1990


def test_the_export_carries_profiles_and_every_version(client: TestClient) -> None:
    client.put("/planning/profile", json={"birth_year": 1988, "target_retirement_year": 2048})
    client.post("/planning/assumptions", json=_version())

    body = client.get("/export").json()

    assert [p["birth_year"] for p in body["member_profiles"]] == [1988]
    assert sorted(v["is_default"] for v in body["planning_assumptions"]) == [False, True]


def test_the_demo_cannot_write_plans(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        assert client.post("/planning/assumptions", json=_version()).status_code == 405
        assert client.put("/planning/profile", json={"birth_year": 1990}).status_code == 405
        assert client.get("/planning/assumptions").status_code == 200
    finally:
        get_settings.cache_clear()
