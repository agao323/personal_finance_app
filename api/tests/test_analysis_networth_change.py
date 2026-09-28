"""Why net worth moved from 31 January to 31 March 2026, in the owner's view.

| Account | 31 Jan | 31 Mar | Change | Reason |
|---|---|---|---|---|
| Checking | $10,000 | $8,000 | -$2,000 | value changed |
| Brokerage | $50,000 | $47,000 | -$3,000 | value changed; $2,000 contributed, so value ~ -$5,000 |
| Rental, 50% then 60% | $200,000 | $240,000 | +$40,000 | stake changed, value flat |
| Car, closed 15 Feb | $8,000 | not counted | -$8,000 | closed |
| HSA, opened 20 Feb | not counted | $3,000 | +$3,000 | opened |
| Mortgage | $300,000 | $300,000 | $0 | not updated |
| Card | $1,000 | $2,500 | -$1,500 | value changed (a bigger debt) |

Net worth -$33,000.00 → -$4,500.00: **+$28,500.00**, and the rows sum to it.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.enums import AccountKind
from app.schemas.common import ViewScope
from app.services.analysis.networth_change import explain
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake, transition_stake

D = dt.date
START, END = D(2026, 1, 31), D(2026, 3, 31)


@pytest.fixture
def world(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
    owner_id: int,
) -> dict[str, int]:
    specs = {
        "checking": ("Checking", "liquid_asset", "checking", None),
        "brokerage": ("Brokerage", "liquid_asset", "brokerage", None),
        "rental": ("Rental", "illiquid_asset", "real_estate", None),
        "car": ("Car", "illiquid_asset", "vehicle", D(2026, 2, 15)),
        "hsa": ("HSA", "illiquid_asset", "hsa", None),
        "mortgage": ("Mortgage", "liability", "mortgage", None),
        "card": ("Card", "liability", "credit_card", None),
    }
    ids = {
        key: make_account(name=name, kind=kind, subtype=subtype, closed_at=closed)
        for key, (name, kind, subtype, closed) in specs.items()
    }
    for key, account in ids.items():
        pct = Decimal("50") if key == "rental" else Decimal("100")
        create_initial_stake(db_session, account, owner_id, D(2025, 1, 1), pct)
    transition_stake(db_session, ids["rental"], owner_id, Decimal("60"), D(2026, 3, 1))

    balances = [
        ("checking", START, "10000"),
        ("checking", END, "8000"),
        ("brokerage", START, "50000"),
        ("brokerage", END, "47000"),
        ("rental", START, "400000"),
        ("rental", END, "400000"),
        ("car", START, "8000"),
        ("hsa", D(2026, 2, 20), "3000"),
        ("mortgage", START, "300000"),
        ("card", START, "1000"),
        ("card", END, "2500"),
    ]
    for key, day, amount in balances:
        record_balance(db_session, ids[key], day, Decimal(amount))
    make_transaction(
        ids["brokerage"],
        D(2026, 3, 2),
        "2000.00",
        "CONTRIBUTION",
        category_ids["Investment Contribution"],
    )
    return ids


def test_each_account_and_its_reason(
    db_session: Session, world: dict[str, int], owner_id: int
) -> None:
    result = explain(db_session, START, END, owner_id)
    rows = {r.account_id: r for r in result.accounts}

    expected = {
        "checking": (Decimal("-2000.00"), ["value_changed"]),
        "brokerage": (Decimal("-3000.00"), ["value_changed"]),
        "rental": (Decimal("40000.00"), ["stake_changed"]),
        "car": (Decimal("-8000.00"), ["closed"]),
        "hsa": (Decimal("3000.00"), ["opened"]),
        "mortgage": (Decimal("0.00"), ["not_updated"]),
        "card": (Decimal("-1500.00"), ["value_changed"]),
    }
    for key, (change, reasons) in expected.items():
        assert (rows[world[key]].change, rows[world[key]].reasons) == (change, reasons), key


def test_the_rows_reconcile_to_the_total(
    db_session: Session, world: dict[str, int], owner_id: int
) -> None:
    result = explain(db_session, START, END, owner_id)

    assert result.start.net_worth == Decimal("-33000.00")
    assert result.end.net_worth == Decimal("-4500.00")
    assert result.change == Decimal("28500.00")
    assert sum((r.change for r in result.accounts), Decimal("0")) == result.change
    assert result.by_kind[AccountKind.LIABILITY] == Decimal("-1500.00")


def test_flows_separate_contributions_from_value(
    db_session: Session, world: dict[str, int], owner_id: int
) -> None:
    brokerage = next(
        r
        for r in explain(db_session, START, END, owner_id).accounts
        if r.account_id == world["brokerage"]
    )

    assert brokerage.flows == Decimal("2000.00")
    assert brokerage.value_change_estimate == Decimal("-5000.00")


def test_coverage_before_the_first_balance(
    db_session: Session, world: dict[str, int], owner_id: int
) -> None:
    assert explain(db_session, START, END, owner_id).history_reaches_start
    assert not explain(db_session, D(2025, 6, 1), END, owner_id).history_reaches_start


def test_the_tool(db_session: Session, owner_id: int, world: dict[str, int]) -> None:
    ctx = ToolContext(
        today=D(2026, 4, 2),
        user_id=owner_id,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )

    outcome = load_all().run(
        "networth_explain_change", {"from_date": "2026-01-31", "to_date": "2026-03-31"}, ctx
    )
    data = json.loads(outcome.content)["data"]

    assert data["change"].startswith("$28,500.00 [")
    assert data["accounts"][0]["name_text"] == "Rental"
    assert data["accounts"][0]["reasons"] == ["stake_changed"]
    brokerage = next(a for a in data["accounts"] if a["name_text"] == "Brokerage")
    assert brokerage["value_change_estimate"].startswith("-$5,000.00 [")


# ── the reconciliation property ───────────────────────────────────────────────

_account = st.tuples(
    st.sampled_from(["liquid_asset", "illiquid_asset", "liability"]),
    st.sampled_from(["100", "50", "33.33", "12.5"]),
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=120),
            st.decimals(min_value=0, max_value=1_000_000, places=2, allow_nan=False),
        ),
        min_size=1,
        max_size=4,
    ),
    st.one_of(st.none(), st.integers(min_value=1, max_value=120)),
)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(accounts=st.lists(_account, min_size=1, max_size=5), household=st.booleans())
def test_changes_always_sum_to_the_total(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    accounts: list[tuple[str, str, list[tuple[int, Decimal]], int | None]],
    household: bool,
) -> None:
    """Whatever the histories, stakes and closures, the parts add up to the whole."""
    base = D(2026, 1, 1)
    savepoint = db_session.begin_nested()
    try:
        for index, (kind, pct, balances, closes_after) in enumerate(accounts):
            closed = base + dt.timedelta(days=closes_after) if closes_after else None
            account = make_account(
                name=f"Account {index}", kind=kind, subtype="other_asset", closed_at=closed
            )
            create_initial_stake(db_session, account, owner_id, base, Decimal(pct))
            for offset, amount in balances:
                record_balance(db_session, account, base + dt.timedelta(days=offset), amount)

        result = explain(db_session, D(2026, 2, 1), D(2026, 4, 30), None if household else owner_id)

        assert sum((r.change for r in result.accounts), Decimal("0")) == result.change
    finally:
        savepoint.rollback()
