"""goals: what the household is aiming for

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28

Ticket 108. Two tables and two enums, hand-written. Each kind's required fields are CHECK
constraints; a savings target's "at least one linked account" spans tables and is enforced by
the service. `debt_free` and `retirement` join `goal_kind` in Wave 12, in their own migration.
Progress is never stored. See `models/goal.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

goal_kind = postgresql.ENUM(
    "spending_limit", "emergency_fund", "savings_target", name="goal_kind", create_type=False
)
goal_status = postgresql.ENUM(
    "active", "achieved", "archived", name="goal_status", create_type=False
)


def upgrade() -> None:
    goal_kind.create(op.get_bind(), checkfirst=False)
    goal_status.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", goal_kind, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("target_amount", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column("target_months", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", goal_status, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind <> 'spending_limit' OR (category_id IS NOT NULL AND target_amount IS NOT NULL)",
            name="ck_goals_spending_limit_fields",
        ),
        sa.CheckConstraint(
            "kind <> 'emergency_fund' OR target_months IS NOT NULL",
            name="ck_goals_emergency_fund_fields",
        ),
        sa.CheckConstraint(
            "kind <> 'savings_target' OR target_amount IS NOT NULL",
            name="ck_goals_savings_target_fields",
        ),
        sa.CheckConstraint(
            "kind = 'spending_limit' OR category_id IS NULL", name="ck_goals_category_only_limits"
        ),
        sa.CheckConstraint(
            "kind = 'emergency_fund' OR target_months IS NULL", name="ck_goals_months_only_fund"
        ),
        sa.CheckConstraint(
            "target_amount IS NULL OR target_amount > 0", name="ck_goals_target_amount_positive"
        ),
        sa.CheckConstraint(
            "target_months IS NULL OR target_months > 0", name="ck_goals_target_months_positive"
        ),
    )
    op.create_index("ix_goals_owner_user_id", "goals", ["owner_user_id"], unique=False)

    op.create_table(
        "goal_accounts",
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("goal_id", "account_id"),
    )
    op.create_index("ix_goal_accounts_account_id", "goal_accounts", ["account_id"], unique=False)


def downgrade() -> None:
    """Drops both tables and both enums. Every goal is lost; they are few and retypeable."""
    op.drop_table("goal_accounts")
    op.drop_table("goals")
    goal_status.drop(op.get_bind(), checkfirst=False)
    goal_kind.drop(op.get_bind(), checkfirst=False)
