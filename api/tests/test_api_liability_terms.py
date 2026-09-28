"""Liability terms: liabilities only, promotional rates, staleness, export, and `debt_terms`.

The migration's round trip is `test_schema.test_upgrade_downgrade_upgrade_is_clean`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.advisor import grounding, render
from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.account import OwnershipStake
from app.models.liability_terms import LiabilityTerms
from app.schemas.common import ViewScope
from app.services import liability_terms as terms_service
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake

JAN = dt.date(2026, 1, 1)
TODAY = dt.date.today()


@pytest.fixture
def card(db_session: Session, make_account: Callable[..., int], owner_id: int) -> int:
    account = make_account(name="Card", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, account, owner_id, JAN)
    record_balance(db_session, account, TODAY, Decimal("1250.00"))
    return account


def _terms(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "apr_pct_thousandths": 24_990,
        "minimum_payment_cents": 3_500,
        "credit_limit_cents": 500_000,
    }
    body.update(overrides)
    return body


# ── the API ───────────────────────────────────────────────────────────────────


def test_terms_are_recorded_and_read_back(client: TestClient, card: int) -> None:
    assert client.get(f"/accounts/{card}/terms").json() is None

    saved = client.put(f"/accounts/{card}/terms", json=_terms())

    assert saved.status_code == 200
    body = client.get(f"/accounts/{card}/terms").json()
    assert body["apr_pct_thousandths"] == 24_990
    assert body["effective_apr_pct_thousandths"] == 24_990
    assert (body["minimum_payment_cents"], body["credit_limit_cents"]) == (3_500, 500_000)
    assert body["as_of"] == TODAY.isoformat()  # defaults to today
    assert body["stale"] is False


def test_an_asset_account_has_no_terms(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    savings = make_account(name="Savings", subtype="savings")

    response = client.put(f"/accounts/{savings}/terms", json=_terms())

    assert response.status_code == 422
    assert "not a liability" in response.json()["detail"]


def test_an_unknown_account_is_not_found(client: TestClient) -> None:
    assert client.get("/accounts/999999/terms").status_code == 404
    assert client.put("/accounts/999999/terms", json=_terms()).status_code == 404


def test_a_promotional_rate_applies_through_its_end_date(client: TestClient, card: int) -> None:
    ends = TODAY + dt.timedelta(days=30)

    body = client.put(
        f"/accounts/{card}/terms",
        json=_terms(promo_apr_pct_thousandths=0, promo_ends_on=ends.isoformat()),
    ).json()

    assert body["effective_apr_pct_thousandths"] == 0
    assert body["promo_ends_on"] == ends.isoformat()


def test_an_ended_promotion_gives_way_to_the_apr(client: TestClient, card: int) -> None:
    ended = TODAY - dt.timedelta(days=1)

    body = client.put(
        f"/accounts/{card}/terms",
        json=_terms(promo_apr_pct_thousandths=0, promo_ends_on=ended.isoformat()),
    ).json()

    assert body["effective_apr_pct_thousandths"] == 24_990


def test_a_promotion_needs_its_end_date(client: TestClient, card: int) -> None:
    response = client.put(f"/accounts/{card}/terms", json=_terms(promo_apr_pct_thousandths=0))

    assert response.status_code == 422


@pytest.mark.parametrize(("age", "stale"), [(365, False), (366, True)])
def test_terms_go_stale_after_a_year(client: TestClient, card: int, age: int, stale: bool) -> None:
    as_of = TODAY - dt.timedelta(days=age)

    body = client.put(f"/accounts/{card}/terms", json=_terms(as_of=as_of.isoformat())).json()

    assert body["stale"] is stale


def test_the_export_carries_terms(client: TestClient, card: int) -> None:
    client.put(f"/accounts/{card}/terms", json=_terms(apr_pct_thousandths=6_875))

    (terms,) = client.get("/export").json()["liability_terms"]

    assert (terms["account_id"], terms["apr"]) == (card, "6.875")


# ── the database ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fields",
    [
        {"apr": Decimal("-1")},
        {"apr": Decimal("101")},
        {"apr": Decimal("5"), "promo_apr": Decimal("0")},  # no end date
        {"apr": Decimal("5"), "credit_limit": Decimal("0")},
        {"apr": Decimal("5"), "term_months": 0},
    ],
)
def test_the_database_refuses_impossible_terms(
    db_session: Session, card: int, fields: dict[str, Any]
) -> None:
    db_session.add(LiabilityTerms(account_id=card, as_of=TODAY, **fields))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_staleness_is_counted_in_days() -> None:
    terms = LiabilityTerms(account_id=1, apr=Decimal("5"), as_of=dt.date(2025, 9, 28))

    assert terms_service.is_stale(terms, dt.date(2026, 9, 28)) is False  # 365 days
    assert terms_service.is_stale(terms, dt.date(2026, 9, 29)) is True  # 366 days


# ── the advisor ───────────────────────────────────────────────────────────────


def test_an_apr_renders_to_three_decimals_and_grounds() -> None:
    assert render.rate(6875) == "6.875%"
    assert render.rate(24990) == "24.990%"
    figures = render.figures_in('{"apr_pct":"6.875% [c3.debts.0.apr_pct]"}')
    assert figures["c3.debts.0.apr_pct"].unit == "pct_thousandths"
    assert figures["c3.debts.0.apr_pct"].value == 6875
    evidence = grounding.Evidence(figures=figures)

    statuses = {
        text: [f.status.value for f in grounding.check(text, evidence).figures]
        for text in ("6.875%", "6.88%", "6.9%", "7%", "6.876%", "{{c3.debts.0.apr_pct}}")
    }

    assert statuses == {
        "6.875%": ["matched"],
        "6.88%": ["matched"],
        "6.9%": ["matched"],
        "7%": ["matched"],
        "6.876%": ["unverified"],
        "{{c3.debts.0.apr_pct}}": ["verified"],
    }


def test_debt_terms_lists_each_debt_with_its_terms_or_their_absence(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
    card: int,
) -> None:
    db_session.add(
        LiabilityTerms(
            account_id=card,
            apr=Decimal("24.990"),
            credit_limit=Decimal("5000.00"),
            minimum_payment=Decimal("35.00"),
            as_of=TODAY,
        )
    )
    loan = make_account(name="Car loan", kind="liability", subtype="auto_loan")
    for user in (owner_id, partner_id):
        db_session.add(
            OwnershipStake(
                account_id=loan, owner_user_id=user, percentage=Decimal("50"), effective_from=JAN
            )
        )
    record_balance(db_session, loan, TODAY, Decimal("9000.00"))
    db_session.flush()
    ctx = ToolContext(
        today=TODAY,
        user_id=owner_id,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )

    outcome = load_all().run("debt_terms", {"view": None}, ctx)

    assert outcome.status == "ok"
    content = outcome.content
    assert "24.990% [c1.debts.0.apr_pct]" in content
    assert "25.00% [c1.debts.0.utilisation_pct]" in content  # 1,250 of 5,000
    assert '"terms_recorded":false' in content
    assert "$9,000.00 [c1.debts.1.balance]" in content
    assert "$4,500.00 [c1.debts.1.share]" in content  # the asker's half
    assert '"without_terms_count":1' in content
