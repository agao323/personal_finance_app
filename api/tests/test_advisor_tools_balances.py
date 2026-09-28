"""Balance tools against a household worked out by hand, on 27 September 2026.

| Account | Kind | Balance | Mine | Household |
|---|---|---|---|---|
| Checking | liquid | $10,000.00 | 100% → $10,000.00 | $10,000.00 |
| Joint savings | liquid | $20,000.00 | 50% → $10,000.00 | 100% → $20,000.00 |
| Brokerage | liquid, **stale** (28 June, 91 days) | $50,000.00 | $50,000.00 | $50,000.00 |
| Rental | illiquid, 50% outside | $420,000.00 | 50% → $210,000.00 | 50% → $210,000.00 |
| Mortgage | liability | $300,000.00 | 60% → $180,000.00 | 100% → $300,000.00 |
| Old car | closed 1 August | $8,000.00 | excluded | excluded |

Mine: assets $280,000.00, liabilities $180,000.00, net worth **$100,000.00**.
Household: assets $290,000.00, liabilities $300,000.00, net worth **-$10,000.00**.

Spending: $1,000.00 of groceries in each of June, July and August, so runway is 70.0
months on my $70,000.00 of liquid assets and 80.0 on the household's $80,000.00.
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
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake

TODAY = dt.date(2026, 9, 27)


@pytest.fixture
def world(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
    owner_id: int,
    partner_id: int,
) -> dict[str, int]:
    def account(name: str, kind: str, subtype: str, **kwargs: Any) -> int:
        return make_account(name=name, kind=kind, subtype=subtype, **kwargs)

    ids = {
        "checking": account("Checking", "liquid_asset", "checking"),
        "joint": account("Joint savings", "liquid_asset", "savings"),
        "brokerage": account("Brokerage", "liquid_asset", "brokerage"),
        "rental": account("Rental", "illiquid_asset", "real_estate"),
        "mortgage": account("Mortgage", "liability", "mortgage"),
        "car": account("Old car", "illiquid_asset", "vehicle", closed_at=dt.date(2026, 8, 1)),
        "card": account("Card", "liability", "credit_card"),
    }
    since = dt.date(2025, 1, 1)
    stakes = [
        ("checking", owner_id, "100"),
        ("joint", owner_id, "50"),
        ("joint", partner_id, "50"),
        ("brokerage", owner_id, "100"),
        ("rental", owner_id, "50"),
        ("mortgage", owner_id, "60"),
        ("mortgage", partner_id, "40"),
        ("car", owner_id, "100"),
        ("card", owner_id, "100"),
    ]
    for name, user, pct in stakes:
        create_initial_stake(db_session, ids[name], user, since, Decimal(pct))

    balances = [
        ("checking", dt.date(2026, 9, 1), "10000.00"),
        ("joint", dt.date(2026, 9, 1), "20000.00"),
        ("brokerage", dt.date(2026, 6, 28), "50000.00"),
        ("rental", dt.date(2026, 9, 1), "420000.00"),
        ("mortgage", dt.date(2026, 9, 1), "300000.00"),
        ("car", dt.date(2026, 1, 1), "8000.00"),
    ]
    for name, day, amount in balances:
        record_balance(db_session, ids[name], day, Decimal(amount))

    for month in (6, 7, 8):
        make_transaction(
            ids["card"], dt.date(2026, month, 10), "-1000.00", "GROCER", category_ids["Groceries"]
        )
    return ids


@pytest.fixture
def ctx(db_session: Session, owner_id: int) -> ToolContext:
    return ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )


def call(ctx: ToolContext, tool: str, **args: Any) -> dict[str, Any]:
    outcome = load_all().run(tool, args, ctx)
    assert outcome.status is LookupStatus.OK, outcome.content
    body: dict[str, Any] = json.loads(outcome.content)
    return body


def figure(text: str) -> str:
    """`$100,000.00 [c1.net_worth]` → `$100,000.00`."""
    return text.split(" [")[0]


# ── networth_get ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("view", "net_worth", "assets", "liabilities"),
    [
        ("mine", "$100,000.00", "$280,000.00", "$180,000.00"),
        ("household", "-$10,000.00", "$290,000.00", "$300,000.00"),
    ],
)
def test_net_worth_in_each_view(
    world: dict[str, int],
    ctx: ToolContext,
    view: str,
    net_worth: str,
    assets: str,
    liabilities: str,
) -> None:
    body = call(ctx, "networth_get", view=view)

    assert body["view"] == view
    assert figure(body["data"]["net_worth"]) == net_worth
    assert figure(body["data"]["assets"]) == assets
    assert figure(body["data"]["liabilities"]) == liabilities


def test_the_conversation_view_is_the_default(world: dict[str, int], ctx: ToolContext) -> None:
    ctx.view = ViewScope.HOUSEHOLD

    assert figure(call(ctx, "networth_get")["data"]["net_worth"]) == "-$10,000.00"


def test_each_account_shows_its_share_and_staleness(
    world: dict[str, int], ctx: ToolContext
) -> None:
    body = call(ctx, "networth_get", view="mine")
    accounts = {a["account_id"]: a for a in body["data"]["accounts"]}

    rental = accounts[world["rental"]]
    assert figure(rental["balance"]) == "$420,000.00"
    assert figure(rental["share"]) == "$210,000.00"
    assert figure(rental["stake"]) == "50.00%"
    assert accounts[world["brokerage"]]["stale"] is True
    assert world["car"] not in accounts
    assert body["stale"] is True
    assert body["data"]["stale_account_count"] == 1


def test_concise_leaves_out_the_accounts(world: dict[str, int], ctx: ToolContext) -> None:
    assert "accounts" not in call(ctx, "networth_get", detail="concise")["data"]


def test_a_future_date_is_refused(world: dict[str, int], ctx: ToolContext) -> None:
    outcome = load_all().run("networth_get", {"as_of": "2027-01-01"}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "after today" in outcome.content


# ── networth_series ───────────────────────────────────────────────────────────


def test_the_series_ends_on_the_same_figure(world: dict[str, int], ctx: ToolContext) -> None:
    body = call(ctx, "networth_series", view="mine", start="2026-01-01")

    points = body["data"]["points"]
    assert points[-1]["as_of"] == "2026-09-27"
    assert figure(points[-1]["net_worth"]) == "$100,000.00"
    assert body["data"]["coverage"]["earliest_snapshot"] == "2026-01-01"
    assert body["data"]["coverage"]["starts_after_requested_start"] is False


def test_coverage_says_when_history_is_short(world: dict[str, int], ctx: ToolContext) -> None:
    body = call(ctx, "networth_series", start="2025-06-01")

    assert body["data"]["coverage"]["starts_after_requested_start"] is True
    assert body["data"]["points"][0]["as_of"] == "2026-01-01"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"start": "2026-01-01", "interval": "day"}, "92 days"),
        ({"start": "2010-01-01", "interval": "month"}, "120 points"),
        ({"start": "2026-09-01", "end": "2026-08-01"}, "on or before"),
    ],
)
def test_series_bounds(
    world: dict[str, int], ctx: ToolContext, args: dict[str, str], message: str
) -> None:
    outcome = load_all().run("networth_series", args, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert message in outcome.content


# ── accounts_list ─────────────────────────────────────────────────────────────


def test_accounts_list_excludes_closed_unless_asked(
    world: dict[str, int], ctx: ToolContext
) -> None:
    open_ids = {a["account_id"] for a in call(ctx, "accounts_list")["data"]["accounts"]}
    all_ids = {
        a["account_id"] for a in call(ctx, "accounts_list", include_closed=True)["data"]["accounts"]
    }

    assert world["car"] not in open_ids
    assert world["car"] in all_ids


def test_accounts_list_shows_the_household_share(world: dict[str, int], ctx: ToolContext) -> None:
    rows = {
        a["account_id"]: a for a in call(ctx, "accounts_list", view="household")["data"]["accounts"]
    }

    assert figure(rows[world["joint"]]["share"]) == "$20,000.00"
    assert figure(rows[world["mortgage"]]["stake"]) == "100.00%"


# ── accounts_history ──────────────────────────────────────────────────────────


def test_history_shows_balances_and_stakes_without_naming_anyone(
    world: dict[str, int], ctx: ToolContext
) -> None:
    body = call(ctx, "accounts_history", account_id=world["mortgage"])

    assert [figure(s["balance"]) for s in body["data"]["snapshots"]] == ["$300,000.00"]
    owners = sorted(s["owner"] for s in body["data"]["stakes"])
    assert owners == ["another household member", "you"]
    assert "partner" not in json.dumps(body).lower()


def test_a_long_history_is_cut_to_month_ends(
    world: dict[str, int], ctx: ToolContext, db_session: Session
) -> None:
    day = dt.date(2026, 1, 1)
    for offset in range(130):
        record_balance(
            db_session, world["checking"], day + dt.timedelta(days=offset), Decimal(1000 + offset)
        )

    body = call(ctx, "accounts_history", account_id=world["checking"])

    assert body["data"]["downsampled_to_month_ends"] is True
    assert [s["as_of"][:7] for s in body["data"]["snapshots"]] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-09",
    ]


def test_an_unknown_account_names_the_way_out(world: dict[str, int], ctx: ToolContext) -> None:
    outcome = load_all().run("accounts_history", {"account_id": 999_999}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "accounts_list" in outcome.content


# ── runway_get ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("view", "liquid", "months"),
    [("mine", "$70,000.00", "70.0"), ("household", "$80,000.00", "80.0")],
)
def test_runway_scope_changes_liquid_assets_only(
    world: dict[str, int], ctx: ToolContext, view: str, liquid: str, months: str
) -> None:
    body = call(ctx, "runway_get", view=view)
    three = next(w for w in body["data"]["windows"] if w["months"] == 3)

    assert figure(body["data"]["liquid_assets"]) == liquid
    assert figure(three["average_monthly_spend"]) == "$1,000.00"
    assert figure(three["runway_months"]) == f"{months} months"
    assert body["data"]["current_month_excluded"] is True
