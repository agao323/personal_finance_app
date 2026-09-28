"""Goal progress, by hand: each kind, a joint account in both scopes, a limit passed mid-month.

Plus the three goal findings, `runway_low` standing down for an emergency-fund goal, the goal
tools, and `GoalRead.progress` over the API.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.account import OwnershipStake
from app.models.enums import GoalKind, GoalStatus
from app.models.goal import Goal, GoalAccount
from app.schemas.advisor import FindingKind
from app.schemas.common import ViewScope
from app.services.analysis import goals as goal_analysis
from app.services.balances import record_balance
from app.services.findings import findings
from app.services.ownership import create_initial_stake

TODAY = dt.date(2026, 9, 15)  # mid-September: 15 of 30 days
JAN = dt.date(2026, 1, 1)
REGISTRY = load_all()


def _goal(db: Session, **fields: Any) -> Goal:
    created = fields.pop("created", dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    accounts = fields.pop("accounts", [])
    goal = Goal(name=fields.pop("name", "A goal"), created_at=created, **fields)
    goal.links = [GoalAccount(account_id=a) for a in accounts]
    db.add(goal)
    db.flush()
    return goal


@pytest.fixture
def card(make_account: Callable[..., int], owner_id: int, db_session: Session) -> int:
    account = make_account(name="Card", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, account, owner_id, JAN)
    return account


# ── spending limits ───────────────────────────────────────────────────────────


def test_a_spending_limit_passed_mid_month(
    db_session: Session,
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    restaurants = category_ids["Restaurants"]
    make_transaction(card, dt.date(2026, 9, 3), "-250.00", category_id=restaurants)
    make_transaction(card, dt.date(2026, 9, 12), "-175.50", category_id=restaurants)
    make_transaction(card, dt.date(2026, 8, 20), "-310.00", category_id=restaurants)
    make_transaction(card, dt.date(2026, 9, 16), "-999.00", category_id=restaurants)  # after today
    goal = _goal(
        db_session,
        kind=GoalKind.SPENDING_LIMIT,
        category_id=restaurants,
        target_amount=Decimal("400.00"),
    )

    result = goal_analysis.progress(db_session, goal, TODAY)

    assert result.month_to_date == Decimal("425.50")
    assert result.last_month == Decimal("310.00")
    assert result.on_track is False
    assert result.progress_bps == 10638  # 425.50 / 400.00 = 106.375% → 106.38%, half up


def test_a_spending_limit_on_pace(
    db_session: Session,
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    make_transaction(card, dt.date(2026, 9, 5), "-200.00", category_id=category_ids["Restaurants"])
    goal = _goal(
        db_session,
        kind=GoalKind.SPENDING_LIMIT,
        category_id=category_ids["Restaurants"],
        target_amount=Decimal("400.00"),
    )

    # $200 by the 15th of a 30-day month is exactly the pro-rata share of $400.
    assert goal_analysis.progress(db_session, goal, TODAY).on_track is True
    assert goal_analysis.progress(db_session, goal, dt.date(2026, 9, 14)).on_track is False


def test_a_parent_category_counts_its_children(
    db_session: Session,
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    from sqlalchemy import select

    from app.models.transaction import Category

    restaurants = db_session.get(Category, category_ids["Restaurants"])
    assert restaurants is not None and restaurants.parent_id is not None
    siblings = (
        db_session.execute(select(Category.id).where(Category.parent_id == restaurants.parent_id))
        .scalars()
        .all()
    )
    for index, category_id in enumerate(siblings[:2]):
        make_transaction(card, dt.date(2026, 9, 2 + index), "-10.00", category_id=category_id)
    goal = _goal(
        db_session,
        kind=GoalKind.SPENDING_LIMIT,
        category_id=restaurants.parent_id,
        target_amount=Decimal("100.00"),
    )

    assert goal_analysis.progress(db_session, goal, TODAY).month_to_date == Decimal("10.00") * min(
        2, len(siblings)
    )


# ── savings targets ───────────────────────────────────────────────────────────


@pytest.fixture
def joint(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> int:
    """A savings account owned 50/50 by the owner and the partner, holding $10,000.00."""
    account = make_account(name="Joint savings", subtype="savings")
    for user in (owner_id, partner_id):
        db_session.add(
            OwnershipStake(
                account_id=account, owner_user_id=user, percentage=Decimal("50"), effective_from=JAN
            )
        )
    record_balance(db_session, account, dt.date(2026, 9, 1), Decimal("10000.00"))
    return account


def test_a_savings_target_in_both_scopes(db_session: Session, joint: int, owner_id: int) -> None:
    household = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        target_amount=Decimal("40000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )
    mine = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        owner_user_id=owner_id,
        target_amount=Decimal("40000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )

    ours = goal_analysis.progress(db_session, household, TODAY)
    yours = goal_analysis.progress(db_session, mine, TODAY)

    assert (ours.saved, ours.remaining) == (Decimal("10000.00"), Decimal("30000.00"))
    assert (yours.saved, yours.remaining) == (Decimal("5000.00"), Decimal("35000.00"))
    # Three calendar months to December: 30,000 / 3 and 35,000 / 3, rounded once, half up.
    assert ours.monthly_needed == Decimal("10000.00")
    assert yours.monthly_needed == Decimal("11666.67")
    assert (ours.progress_bps, yours.progress_bps) == (2500, 1250)


def test_a_savings_target_is_on_track_on_the_straight_line(db_session: Session, joint: int) -> None:
    # Set on 1 January for 31 December: by 15 September (257 of 364 days) the line asks for
    # 40,000 * 257 / 364 = 28,241.76. Saved is 10,000: behind.
    behind = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        target_amount=Decimal("40000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )
    # A 12,000 target: the line asks for 8,472.53 by now, and 10,000 is saved.
    ahead = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        target_amount=Decimal("12000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )

    assert goal_analysis.progress(db_session, behind, TODAY).on_track is False
    assert goal_analysis.progress(db_session, ahead, TODAY).on_track is True


def test_a_past_date_needs_everything_now(db_session: Session, joint: int) -> None:
    goal = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        target_amount=Decimal("15000.00"),
        target_date=dt.date(2026, 6, 30),
        accounts=[joint],
    )

    result = goal_analysis.progress(db_session, goal, TODAY)

    assert (result.monthly_needed, result.on_track) == (Decimal("5000.00"), False)


def test_a_stale_linked_balance_marks_progress_stale(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    old = make_account(name="Old savings", subtype="savings")
    create_initial_stake(db_session, old, owner_id, JAN)
    record_balance(db_session, old, dt.date(2026, 3, 1), Decimal("100.00"))
    goal = _goal(
        db_session, kind=GoalKind.SAVINGS_TARGET, target_amount=Decimal("500.00"), accounts=[old]
    )

    assert goal_analysis.progress(db_session, goal, TODAY).stale is True


# ── emergency funds ───────────────────────────────────────────────────────────


@pytest.fixture
def cash_and_spending(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    """$6,000.00 of cash and $1,000.00 of spending in each of the six months before September."""
    checking = make_account(name="Checking", subtype="checking")
    create_initial_stake(db_session, checking, owner_id, JAN)
    record_balance(db_session, checking, dt.date(2026, 9, 1), Decimal("6000.00"))
    for month in range(3, 9):
        make_transaction(
            card, dt.date(2026, month, 10), "-1000.00", category_id=category_ids["Groceries"]
        )


def test_an_emergency_fund_below_target(db_session: Session, cash_and_spending: None) -> None:
    goal = _goal(db_session, kind=GoalKind.EMERGENCY_FUND, target_months=Decimal("9"))

    result = goal_analysis.progress(db_session, goal, TODAY)

    assert result.runway_months_tenths == 60  # 6,000 / 1,000
    assert result.on_track is False
    assert result.progress_bps == 6667  # 6 of 9 months


def test_an_emergency_fund_at_target(db_session: Session, cash_and_spending: None) -> None:
    goal = _goal(db_session, kind=GoalKind.EMERGENCY_FUND, target_months=Decimal("6"))

    assert goal_analysis.progress(db_session, goal, TODAY).on_track is True


# ── findings ──────────────────────────────────────────────────────────────────


def _kinds(db: Session, owner_id: int) -> list[FindingKind]:
    return [f.kind for f in findings(db, TODAY, ViewScope.HOUSEHOLD, owner_id)]


def test_findings_for_each_goal_that_needs_attention(
    db_session: Session,
    owner_id: int,
    cash_and_spending: None,
    joint: int,
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    make_transaction(card, dt.date(2026, 9, 3), "-500.00", category_id=category_ids["Restaurants"])
    _goal(
        db_session,
        kind=GoalKind.SPENDING_LIMIT,
        category_id=category_ids["Restaurants"],
        target_amount=Decimal("400.00"),
    )
    # $6,000 of checking and the joint $10,000 cover 16 months: under a 24-month target.
    _goal(db_session, kind=GoalKind.EMERGENCY_FUND, target_months=Decimal("24"))
    _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        name="House",
        target_amount=Decimal("40000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )

    found = findings(db_session, TODAY, ViewScope.HOUSEHOLD, owner_id)
    kinds = [f.kind for f in found]

    assert FindingKind.SPENDING_LIMIT_EXCEEDED in kinds
    assert FindingKind.EMERGENCY_FUND_BELOW_TARGET in kinds
    assert FindingKind.GOAL_OFF_TRACK in kinds
    assert FindingKind.RUNWAY_LOW not in kinds
    exceeded = next(f for f in found if f.kind is FindingKind.SPENDING_LIMIT_EXCEEDED)
    assert exceeded.title == "Restaurants is over its $400.00 monthly limit"
    assert (
        exceeded.action is not None and exceeded.action.category_id == category_ids["Restaurants"]
    )
    assert exceeded.impact_cents == 10_000
    house = next(f for f in found if f.kind is FindingKind.GOAL_OFF_TRACK)
    assert house.title == "House is behind: $10,000.00 of $40,000.00"


def test_runway_low_stands_down_only_for_an_emergency_fund_goal(
    db_session: Session,
    owner_id: int,
    make_account: Callable[..., int],
    card: int,
    category_ids: dict[str, int],
    make_transaction: Callable[..., int],
) -> None:
    checking = make_account(name="Checking", subtype="checking")
    create_initial_stake(db_session, checking, owner_id, JAN)
    record_balance(db_session, checking, dt.date(2026, 9, 1), Decimal("1000.00"))
    for month in range(3, 9):
        make_transaction(
            card, dt.date(2026, month, 10), "-1000.00", category_id=category_ids["Groceries"]
        )

    assert FindingKind.RUNWAY_LOW in _kinds(db_session, owner_id)

    fund = _goal(db_session, kind=GoalKind.EMERGENCY_FUND, target_months=Decimal("3"))
    assert FindingKind.RUNWAY_LOW not in _kinds(db_session, owner_id)
    assert FindingKind.EMERGENCY_FUND_BELOW_TARGET in _kinds(db_session, owner_id)

    fund.status = GoalStatus.ARCHIVED
    db_session.flush()
    assert FindingKind.RUNWAY_LOW in _kinds(db_session, owner_id)


# ── tools ─────────────────────────────────────────────────────────────────────


def _ctx(db: Session, owner_id: int) -> ToolContext:
    return ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db)
    )


def test_the_goal_tools(db_session: Session, owner_id: int, partner_id: int, joint: int) -> None:
    ours = _goal(
        db_session,
        kind=GoalKind.SAVINGS_TARGET,
        name="House",
        target_amount=Decimal("40000.00"),
        target_date=dt.date(2026, 12, 31),
        accounts=[joint],
    )
    _goal(
        db_session,
        kind=GoalKind.EMERGENCY_FUND,
        owner_user_id=partner_id,
        target_months=Decimal("6"),
    )
    ctx = _ctx(db_session, owner_id)

    listed = REGISTRY.run("goals_list", {}, ctx)
    evaluated = REGISTRY.run("goals_evaluate", {"goal_id": ours.id}, ctx)
    theirs = REGISTRY.run("goals_evaluate", {"goal_id": ours.id + 1}, ctx)

    assert listed.status == "ok"
    assert '"name_text":"House"' in listed.content
    assert "partner" not in listed.content.lower() and listed.content.count("goal_id") == 1
    assert evaluated.status == "ok"
    assert "$10,000.00" in evaluated.content and "$10,000.00 [c2.goals.0.monthly_needed]" in (
        evaluated.content
    )
    assert theirs.status == "invalid_args"


def test_the_planning_tool_flags_the_defaults(db_session: Session, owner_id: int) -> None:
    outcome = REGISTRY.run("planning_profile", {}, _ctx(db_session, owner_id))

    assert outcome.status == "ok"
    assert '"defaults":true' in outcome.content
    assert "5.00% [c1.assumptions.expected_real_return_pct]" in outcome.content
    assert '"birth_year"' not in outcome.content  # null fields are left out


# ── the API ───────────────────────────────────────────────────────────────────


def test_goal_read_carries_progress(client: TestClient, joint: int, db_session: Session) -> None:
    created = client.post(
        "/goals",
        json={
            "kind": "savings_target",
            "name": "House",
            "view": "household",
            "target_amount_cents": 4_000_000,
            "account_ids": [joint],
        },
    ).json()

    progress = created["progress"]
    assert progress["saved_cents"] == 1_000_000
    assert progress["remaining_cents"] == 3_000_000
    assert progress["progress_bps"] == 2500
    assert progress["on_track"] is True  # no date, so no pace to fall behind
