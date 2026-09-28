"""planning: member profiles and append-only assumptions, with a defaults row

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-28

Ticket 109. `member_profiles` holds birth year and target retirement year per person — the year
only, deliberately. `planning_assumptions` is append-only; the latest row wins. This revision
inserts one row marked `is_default` so there is always a set of assumptions to state, and the
advisor says when it is stating the defaults. See `models/planning.py`.

The defaults: a 5% real return, 2.5% inflation, a 3% to 4.5% withdrawal band, a flat 15% on
tax-deferred withdrawals, moderate risk, and a 40/20/35/5/0 mix of US equity, international
equity, bonds, cash and other. They are placeholders to be replaced, not recommendations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

risk_tolerance = postgresql.ENUM(
    "conservative", "moderate", "aggressive", name="risk_tolerance", create_type=False
)
MIX = (
    "target_us_equity_pct",
    "target_intl_equity_pct",
    "target_bonds_pct",
    "target_cash_pct",
    "target_other_pct",
)
BOUNDS = {
    "expected_real_return_bps": (-1000, 2000),
    "inflation_bps": (-500, 2000),
    "withdrawal_low_bps": (0, 1500),
    "withdrawal_high_bps": (0, 1500),
    "tax_deferred_withdrawal_tax_bps": (0, 6000),
}


def upgrade() -> None:
    risk_tolerance.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "member_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=True),
        sa.Column("target_retirement_year", sa.SmallInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100",
            name="ck_member_profiles_birth_year",
        ),
        sa.CheckConstraint(
            "target_retirement_year IS NULL OR target_retirement_year BETWEEN 1900 AND 2200",
            name="ck_member_profiles_retirement_year",
        ),
        sa.CheckConstraint(
            "birth_year IS NULL OR target_retirement_year IS NULL "
            "OR target_retirement_year > birth_year",
            name="ck_member_profiles_retire_after_birth",
        ),
    )

    op.create_table(
        "planning_assumptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expected_real_return_bps", sa.Integer(), nullable=False),
        sa.Column("inflation_bps", sa.Integer(), nullable=False),
        sa.Column("withdrawal_low_bps", sa.Integer(), nullable=False),
        sa.Column("withdrawal_high_bps", sa.Integer(), nullable=False),
        sa.Column("pre65_healthcare_annual", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column("tax_deferred_withdrawal_tax_bps", sa.Integer(), nullable=False),
        sa.Column("risk_tolerance", risk_tolerance, nullable=False),
        *(sa.Column(field, sa.Numeric(precision=5, scale=2), nullable=False) for field in MIX),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        *(
            sa.CheckConstraint(
                f"{field} BETWEEN {low} AND {high}", name=f"ck_planning_assumptions_{field}"
            )
            for field, (low, high) in BOUNDS.items()
        ),
        sa.CheckConstraint(
            "withdrawal_low_bps <= withdrawal_high_bps",
            name="ck_planning_assumptions_withdrawal_band",
        ),
        sa.CheckConstraint(
            "pre65_healthcare_annual IS NULL OR pre65_healthcare_annual >= 0",
            name="ck_planning_assumptions_healthcare",
        ),
        *(
            sa.CheckConstraint(
                f"{field} BETWEEN 0 AND 100", name=f"ck_planning_assumptions_{field}"
            )
            for field in MIX
        ),
        sa.CheckConstraint(
            " + ".join(MIX) + " = 100", name="ck_planning_assumptions_mix_totals_100"
        ),
    )

    op.execute(
        """
        INSERT INTO planning_assumptions (
            is_default, expected_real_return_bps, inflation_bps, withdrawal_low_bps,
            withdrawal_high_bps, tax_deferred_withdrawal_tax_bps, risk_tolerance,
            target_us_equity_pct, target_intl_equity_pct, target_bonds_pct,
            target_cash_pct, target_other_pct
        ) VALUES (true, 500, 250, 300, 450, 1500, 'moderate', 40, 20, 35, 5, 0)
        """
    )


def downgrade() -> None:
    """Drops both tables and the enum. Every stated assumption and profile is lost."""
    op.drop_table("planning_assumptions")
    op.drop_table("member_profiles")
    risk_tolerance.drop(op.get_bind(), checkfirst=False)
