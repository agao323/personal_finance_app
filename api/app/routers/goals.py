"""Goals. Ticket 108; progress is computed on every read by 111's `analysis/goals.py`.

**Each person sees household goals and their own.** Another member's personal goal is a 404,
as a conversation is: whether it exists is not theirs to learn.

**Each kind's fields are checked here with a readable 422**, before the database's `CHECK`
constraints would refuse the same thing less politely. The one rule the database cannot hold —
a savings target needs at least one linked, open account — lives only here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.enums import GoalKind
from app.models.goal import Goal, GoalAccount
from app.models.transaction import Category
from app.schemas.common import ErrorResponse, ViewScope, to_cents
from app.schemas.goal import GoalCreate, GoalProgress, GoalRead, GoalUpdate
from app.services.analysis import goals as goal_analysis

router = APIRouter(
    prefix="/goals",
    tags=["goals"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _visible(user_id: int) -> Any:
    return or_(Goal.owner_user_id.is_(None), Goal.owner_user_id == user_id)


def _require(session: Session, goal_id: int, user_id: int) -> Goal:
    goal = session.execute(
        select(Goal).where(Goal.id == goal_id, _visible(user_id))
    ).scalar_one_or_none()
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


def progress_read(result: goal_analysis.Progress) -> GoalProgress:
    """A computed `Progress` on the wire: money in cents, months in tenths."""

    def cents(value: Decimal | None) -> int | None:
        return None if value is None else to_cents(value)

    return GoalProgress(
        as_of=result.as_of,
        on_track=result.on_track,
        stale=result.stale,
        month_to_date_cents=cents(result.month_to_date),
        last_month_cents=cents(result.last_month),
        runway_months_tenths=result.runway_months_tenths,
        saved_cents=cents(result.saved),
        remaining_cents=cents(result.remaining),
        monthly_needed_cents=cents(result.monthly_needed),
        progress_bps=result.progress_bps,
    )


def _to_read(session: Session, goal: Goal) -> GoalRead:
    category = session.get(Category, goal.category_id) if goal.category_id else None
    return GoalRead(
        id=goal.id,
        kind=goal.kind,
        name=goal.name,
        view=ViewScope.HOUSEHOLD if goal.owner_user_id is None else ViewScope.MINE,
        category_id=goal.category_id,
        category_name=category.name if category else None,
        target_amount_cents=to_cents(goal.target_amount) if goal.target_amount else None,
        target_months_tenths=int(goal.target_months.scaleb(1)) if goal.target_months else None,
        target_date=goal.target_date,
        status=goal.status,
        account_ids=[link.account_id for link in goal.links],
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        progress=progress_read(goal_analysis.progress(session, goal, dt.date.today())),
    )


def _check_fields(
    session: Session,
    kind: GoalKind,
    *,
    category_id: int | None,
    amount_cents: int | None,
    months_tenths: int | None,
    account_ids: list[int],
) -> None:
    """Each kind's required fields, and nothing a kind does not use."""
    if kind is GoalKind.SPENDING_LIMIT:
        if category_id is None or amount_cents is None:
            raise _unprocessable("A spending limit needs a category and a monthly amount.")
        if session.get(Category, category_id) is None:
            raise _unprocessable(f"No category with id {category_id}")
    elif category_id is not None:
        raise _unprocessable("Only a spending limit has a category.")
    if kind is GoalKind.EMERGENCY_FUND:
        if months_tenths is None:
            raise _unprocessable("An emergency fund needs a target in months.")
    elif months_tenths is not None:
        raise _unprocessable("Only an emergency fund has a target in months.")
    if kind is GoalKind.SAVINGS_TARGET:
        if amount_cents is None:
            raise _unprocessable("A savings target needs an amount.")
        if not account_ids:
            raise _unprocessable(
                "A savings target needs at least one account that counts toward it."
            )
        accounts = (
            session.execute(select(Account).where(Account.id.in_(account_ids))).scalars().all()
        )
        if len(accounts) != len(set(account_ids)):
            raise _unprocessable("One of those accounts does not exist.")
        closed = [a.name for a in accounts if a.closed_at is not None]
        if closed:
            raise _unprocessable(
                f"A closed account cannot count toward a goal: {', '.join(closed)}"
            )
    elif account_ids:
        raise _unprocessable("Only a savings target has linked accounts.")


def _money(cents: int | None) -> Decimal | None:
    return None if cents is None else Decimal(cents).scaleb(-2)


def _months(tenths: int | None) -> Decimal | None:
    return None if tenths is None else Decimal(tenths).scaleb(-1)


@router.get("", response_model=list[GoalRead])
def list_goals(session: DbSession, user: CurrentUser) -> list[GoalRead]:
    """Household goals and your own, newest first."""
    goals = session.execute(
        select(Goal).where(_visible(user.id)).order_by(Goal.created_at.desc(), Goal.id.desc())
    ).scalars()
    return [_to_read(session, goal) for goal in goals]


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(session: DbSession, user: CurrentUser, payload: GoalCreate) -> GoalRead:
    """Set a goal. A `household` goal is shared; a `mine` goal is yours alone."""
    _check_fields(
        session,
        payload.kind,
        category_id=payload.category_id,
        amount_cents=payload.target_amount_cents,
        months_tenths=payload.target_months_tenths,
        account_ids=payload.account_ids,
    )
    goal = Goal(
        kind=payload.kind,
        name=payload.name,
        owner_user_id=None if payload.view is ViewScope.HOUSEHOLD else user.id,
        category_id=payload.category_id,
        target_amount=_money(payload.target_amount_cents),
        target_months=_months(payload.target_months_tenths),
        target_date=payload.target_date,
        links=[
            GoalAccount(account_id=account_id) for account_id in dict.fromkeys(payload.account_ids)
        ],
    )
    session.add(goal)
    session.flush()
    session.refresh(goal)
    return _to_read(session, goal)


@router.patch("/{goal_id}", response_model=GoalRead)
def update_goal(
    session: DbSession, user: CurrentUser, goal_id: int, payload: GoalUpdate
) -> GoalRead:
    """Change a goal's name, targets, status or accounts. Its kind and owner are fixed."""
    goal = _require(session, goal_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    category_id = changes.get("category_id", goal.category_id)
    amount_cents = changes.get(
        "target_amount_cents", to_cents(goal.target_amount) if goal.target_amount else None
    )
    months_tenths = changes.get(
        "target_months_tenths",
        int(goal.target_months.scaleb(1)) if goal.target_months else None,
    )
    account_ids = changes.get("account_ids")
    if account_ids is None:
        account_ids = [link.account_id for link in goal.links]
    _check_fields(
        session,
        goal.kind,
        category_id=category_id,
        amount_cents=amount_cents,
        months_tenths=months_tenths,
        account_ids=account_ids,
    )
    if "name" in changes and changes["name"] is not None:
        goal.name = changes["name"]
    goal.category_id = category_id
    goal.target_amount = _money(amount_cents)
    goal.target_months = _months(months_tenths)
    if "target_date" in changes:
        goal.target_date = changes["target_date"]
    if changes.get("status") is not None:
        goal.status = changes["status"]
    if "account_ids" in changes and changes["account_ids"] is not None:
        goal.links = [GoalAccount(account_id=a) for a in dict.fromkeys(changes["account_ids"])]
    session.flush()
    session.refresh(goal)
    return _to_read(session, goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(session: DbSession, user: CurrentUser, goal_id: int) -> Response:
    """Delete a goal. Archiving keeps it instead."""
    session.delete(_require(session, goal_id, user.id))
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
