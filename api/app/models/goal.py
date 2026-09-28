"""Goals: what the household is aiming for, so advice has something to be measured against.

docs/ADVISOR.md#goals-wave-11-migration-in-108. Three kinds, each with its own required fields,
enforced by `CHECK` constraints here and by the service with clearer messages:

- `spending_limit` — a category and a monthly amount;
- `emergency_fund` — a number of months of spending;
- `savings_target` — an amount, optionally by a date, and at least one linked account (the one
  rule a `CHECK` cannot express across tables; the service enforces it).

**Progress is computed, never stored** — like current balance, which is derived from snapshots
rather than written onto `accounts`. `GoalRead.progress` carries it (ticket 111).

**A household goal has no owner**; a personal goal belongs to the member who set it, and only
they see it.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.account import MONEY
from app.models.enums import GoalKind, GoalStatus, pg_enum


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(
            "kind <> 'spending_limit' OR (category_id IS NOT NULL AND target_amount IS NOT NULL)",
            name="ck_goals_spending_limit_fields",
        ),
        CheckConstraint(
            "kind <> 'emergency_fund' OR target_months IS NOT NULL",
            name="ck_goals_emergency_fund_fields",
        ),
        CheckConstraint(
            "kind <> 'savings_target' OR target_amount IS NOT NULL",
            name="ck_goals_savings_target_fields",
        ),
        CheckConstraint(
            "kind = 'spending_limit' OR category_id IS NULL", name="ck_goals_category_only_limits"
        ),
        CheckConstraint(
            "kind = 'emergency_fund' OR target_months IS NULL", name="ck_goals_months_only_fund"
        ),
        CheckConstraint(
            "target_amount IS NULL OR target_amount > 0", name="ck_goals_target_amount_positive"
        ),
        CheckConstraint(
            "target_months IS NULL OR target_months > 0", name="ck_goals_target_months_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[GoalKind] = mapped_column(pg_enum(GoalKind, "goal_kind"), nullable=False)
    #: Typed by a member; untrusted at the advisor's tool boundary like every name.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: NULL is a household goal. RESTRICT: members are deactivated, never deleted.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    #: A savings target's total, or a spending limit per month.
    target_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    #: An emergency fund's target, in months of spending.
    target_months: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    target_date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(
        pg_enum(GoalStatus, "goal_status"), nullable=False, default=GoalStatus.ACTIVE
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    links: Mapped[list[GoalAccount]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", order_by="GoalAccount.account_id"
    )


class GoalAccount(Base):
    """Which accounts count toward a savings target."""

    __tablename__ = "goal_accounts"

    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    #: CASCADE: deleting an account removes it from any goal, as it removes everything else.
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    goal: Mapped[Goal] = relationship(back_populates="links")
