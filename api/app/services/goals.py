"""Goal queries (ticket 108). The router validates and shapes; the queries live here.

**Each person sees household goals and their own**: a goal with no owner, or one they own.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.goal import Goal


def _visible(user_id: int) -> ColumnElement[bool]:
    return or_(Goal.owner_user_id.is_(None), Goal.owner_user_id == user_id)


def visible_goals(session: Session, user_id: int) -> list[Goal]:
    """Household goals and `user_id`'s own, newest first."""
    return list(
        session.execute(
            select(Goal).where(_visible(user_id)).order_by(Goal.created_at.desc(), Goal.id.desc())
        ).scalars()
    )


def visible_goal(session: Session, goal_id: int, user_id: int) -> Goal | None:
    """One goal, or None when it does not exist or belongs to someone else."""
    return session.execute(
        select(Goal).where(Goal.id == goal_id, _visible(user_id))
    ).scalar_one_or_none()


def accounts(session: Session, account_ids: Sequence[int]) -> list[Account]:
    """The accounts with these ids that exist."""
    return list(session.execute(select(Account).where(Account.id.in_(account_ids))).scalars())
