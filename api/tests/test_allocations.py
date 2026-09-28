"""Tax treatment and account-level allocation: defaults, the 100% invariant, and the API.

The migration's round trip is `test_schema.test_upgrade_downgrade_upgrade_is_clean`.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Account, AccountAllocation
from app.models.enums import AccountSubtype, AssetClass, TaxTreatment
from app.services import allocations

JAN = dt.date(2026, 1, 1)
JUL = dt.date(2026, 7, 1)
TODAY = dt.date.today()

_SPEC = importlib.util.spec_from_file_location(
    "revision_0011",
    Path(__file__).parents[1] / "alembic" / "versions" / "0011_tax_and_allocation.py",
)
assert _SPEC is not None and _SPEC.loader is not None
migration = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)


@pytest.fixture
def brokerage(make_account: Callable[..., int]) -> int:
    return make_account(name="Brokerage", kind="liquid_asset", subtype="brokerage")


def _shares(**pcts: str) -> dict[AssetClass, Decimal]:
    return {AssetClass(name): Decimal(pct) for name, pct in pcts.items()}


def _body(effective_from: dt.date, **bps: int) -> dict[str, Any]:
    return {
        "effective_from": effective_from.isoformat(),
        "shares": [{"asset_class": name, "percentage_bps": v} for name, v in bps.items()],
    }


# ── tax treatment ─────────────────────────────────────────────────────────────


def test_the_backfill_matches_the_default_for_every_subtype() -> None:
    assert {AccountSubtype(k): TaxTreatment(v) for k, v in migration.BACKFILL.items()} == (
        allocations.DEFAULT_TAX_TREATMENT
    )
    assert set(allocations.DEFAULT_TAX_TREATMENT) == set(AccountSubtype)


@pytest.mark.parametrize(
    ("subtype", "expected"),
    [
        ("401k", "tax_deferred"),
        ("ira", "tax_deferred"),
        ("roth_ira", "roth"),
        ("hsa", "hsa"),
        ("529", "education"),
        ("brokerage", "taxable"),
        ("checking", "taxable"),
        ("mortgage", "none"),
    ],
)
def test_an_unset_treatment_reads_as_the_subtype_default(
    db_session: Session, make_account: Callable[..., int], subtype: str, expected: str
) -> None:
    account = db_session.get_one(Account, make_account(subtype=subtype))

    assert account.tax_treatment is None
    assert allocations.tax_treatment(account) is TaxTreatment(expected)


def test_a_new_account_stores_its_default_treatment(client: TestClient) -> None:
    body = client.post(
        "/accounts",
        json={"name": "401k", "kind": "illiquid_asset", "subtype": "401k"},
    ).json()

    assert body["tax_treatment"] == "tax_deferred"


def test_the_treatment_is_editable(client: TestClient, make_account: Callable[..., int]) -> None:
    account = make_account(name="Old 401k", kind="illiquid_asset", subtype="401k")

    patched = client.patch(f"/accounts/{account}", json={"tax_treatment": "roth"})

    assert patched.status_code == 200
    assert patched.json()["tax_treatment"] == "roth"
    assert client.get(f"/accounts/{account}").json()["tax_treatment"] == "roth"


# ── the invariant ─────────────────────────────────────────────────────────────


def test_a_transition_closes_the_old_rows_with_no_gap_or_overlap(
    db_session: Session, brokerage: int
) -> None:
    account = db_session.get_one(Account, brokerage)
    allocations.set_allocation(db_session, account, _shares(us_equity="60", bonds="40"), JAN)

    allocations.set_allocation(
        db_session, account, _shares(us_equity="50", intl_equity="30", bonds="20"), JUL
    )

    rows = allocations.history(db_session, brokerage)
    assert {(r.asset_class, r.effective_from, r.effective_to) for r in rows} == {
        (AssetClass.US_EQUITY, JAN, JUL),
        (AssetClass.BONDS, JAN, JUL),
        (AssetClass.US_EQUITY, JUL, None),
        (AssetClass.INTL_EQUITY, JUL, None),
        (AssetClass.BONDS, JUL, None),
    }
    before = allocations.allocation_for(db_session, account, JUL - dt.timedelta(days=1))
    on = allocations.allocation_for(db_session, account, JUL)
    assert before.shares == _shares(us_equity="60", bonds="40")
    assert on.shares == _shares(us_equity="50", intl_equity="30", bonds="20")
    assert allocations.invariant_holds(db_session, brokerage)


@pytest.mark.parametrize(
    "shares",
    [
        {"us_equity": "60", "bonds": "39.99"},  # 99.99
        {"us_equity": "60", "bonds": "40.01"},  # 100.01
        {"us_equity": "100", "bonds": "0"},
    ],
)
def test_the_service_refuses_anything_but_exactly_100(
    db_session: Session, brokerage: int, shares: dict[str, str]
) -> None:
    account = db_session.get_one(Account, brokerage)

    with pytest.raises(allocations.AllocationError):
        allocations.set_allocation(db_session, account, _shares(**shares), JAN)

    assert allocations.history(db_session, brokerage) == []


def test_a_new_allocation_must_start_after_the_last(db_session: Session, brokerage: int) -> None:
    account = db_session.get_one(Account, brokerage)
    allocations.set_allocation(db_session, account, _shares(cash="100"), JUL)

    with pytest.raises(allocations.AllocationError, match="starts on or after"):
        allocations.set_allocation(db_session, account, _shares(bonds="100"), JUL)
    with pytest.raises(allocations.AllocationError, match="starts on or after"):
        allocations.set_allocation(db_session, account, _shares(bonds="100"), JAN)


def test_the_invariant_check_catches_a_short_row_written_around_the_service(
    db_session: Session, brokerage: int
) -> None:
    db_session.add(
        AccountAllocation(
            account_id=brokerage,
            asset_class=AssetClass.US_EQUITY,
            percentage=Decimal("99.99"),
            effective_from=JAN,
        )
    )
    db_session.flush()

    assert not allocations.invariant_holds(db_session, brokerage)


@pytest.mark.parametrize(
    "fields",
    [
        {"percentage": Decimal("0")},
        {"percentage": Decimal("100.01")},
        {"percentage": Decimal("50"), "effective_to": JAN},
    ],
)
def test_the_database_refuses_impossible_rows(
    db_session: Session, brokerage: int, fields: dict[str, Any]
) -> None:
    db_session.add(
        AccountAllocation(
            account_id=brokerage, asset_class=AssetClass.CASH, effective_from=JAN, **fields
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


# ── derived, unknown, not applicable ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "subtype", "status", "shares"),
    [
        ("liquid_asset", "savings", "derived", {AssetClass.CASH: Decimal("100")}),
        ("illiquid_asset", "real_estate", "derived", {AssetClass.REAL_ESTATE: Decimal("100")}),
        ("illiquid_asset", "vehicle", "derived", {AssetClass.OTHER: Decimal("100")}),
        ("liquid_asset", "brokerage", "unknown", {}),
        ("illiquid_asset", "hsa", "unknown", {}),
        ("liability", "mortgage", "not_applicable", {}),
    ],
)
def test_what_each_kind_of_account_reports_without_rows(
    db_session: Session,
    make_account: Callable[..., int],
    kind: str,
    subtype: str,
    status: str,
    shares: dict[AssetClass, Decimal],
) -> None:
    account = db_session.get_one(Account, make_account(kind=kind, subtype=subtype))

    current = allocations.allocation_for(db_session, account, TODAY)

    assert (current.status, current.shares) == (status, shares)


def test_a_derived_account_refuses_a_recorded_allocation(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account = db_session.get_one(Account, make_account(subtype="savings"))

    with pytest.raises(allocations.AllocationError, match="follows from what it is"):
        allocations.set_allocation(db_session, account, _shares(bonds="100"), JAN)


# ── the API ───────────────────────────────────────────────────────────────────


def test_an_allocation_is_set_and_read_back(client: TestClient, brokerage: int) -> None:
    assert client.get(f"/accounts/{brokerage}/allocations").json() == {
        "status": "unknown",
        "shares": [],
        "history": [],
    }

    first = client.post(
        f"/accounts/{brokerage}/allocations", json=_body(JAN, us_equity=6000, bonds=4000)
    )
    second = client.post(
        f"/accounts/{brokerage}/allocations", json=_body(JUL, us_equity=7000, bonds=3000)
    )

    assert (first.status_code, second.status_code) == (201, 201)
    body = client.get(f"/accounts/{brokerage}/allocations").json()
    if TODAY >= JUL:
        assert body["status"] == "recorded"
        assert [(s["asset_class"], s["percentage_bps"]) for s in body["shares"]] == [
            ("us_equity", 7000),  # the enum's order, as the history is
            ("bonds", 3000),
        ]
    assert [(r["asset_class"], r["effective_to"]) for r in body["history"]] == [
        ("us_equity", None),  # newest first, then in the enum's order
        ("bonds", None),
        ("us_equity", JUL.isoformat()),
        ("bonds", JUL.isoformat()),
    ]


def test_the_api_refuses_a_total_of_99_99(client: TestClient, brokerage: int) -> None:
    response = client.post(
        f"/accounts/{brokerage}/allocations", json=_body(JAN, us_equity=6000, bonds=3999)
    )

    assert response.status_code == 422
    assert "99.99%" in str(response.json())


def test_the_api_refuses_a_class_twice(client: TestClient, brokerage: int) -> None:
    body = _body(JAN, us_equity=5000)
    body["shares"].append({"asset_class": "us_equity", "percentage_bps": 5000})

    assert client.post(f"/accounts/{brokerage}/allocations", json=body).status_code == 422


def test_the_api_refuses_an_allocation_on_a_derived_account(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    savings = make_account(subtype="savings")

    response = client.post(f"/accounts/{savings}/allocations", json=_body(JAN, bonds=10000))

    assert response.status_code == 422
    assert "follows from what it is" in response.json()["detail"]
    assert client.get(f"/accounts/{savings}/allocations").json()["status"] == "derived"


def test_an_unknown_account_is_not_found(client: TestClient) -> None:
    assert client.get("/accounts/999999/allocations").status_code == 404
    assert client.post("/accounts/999999/allocations", json=_body(JAN, cash=10000)).status_code == (
        404
    )


def test_the_export_carries_allocations(client: TestClient, brokerage: int) -> None:
    client.post(f"/accounts/{brokerage}/allocations", json=_body(JAN, cash=10000))

    (row,) = client.get("/export").json()["account_allocations"]

    assert (row["account_id"], row["asset_class"], row["percentage"]) == (
        brokerage,
        "cash",
        "100.00",
    )
