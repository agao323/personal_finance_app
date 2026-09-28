"""Who is planning, and the assumptions every projection and piece of advice rests on.

docs/ADVISOR.md#planning-profile-and-assumptions-wave-11-migration-in-109.

- **`member_profiles`** — birth year and target retirement year, per person. Birth *year* only:
  it is the most personal field in the schema, and the projections need nothing finer.
- **`planning_assumptions`** — append-only; the latest row wins. A projection records the id it
  used, so it can be reproduced with the assumptions it was made under. The migration inserts
  one row marked `is_default`, so there is always something to state — and the advisor says
  when what it states is the default.

Rates are basis points (500 = 5.00%); the target mix is `NUMERIC(5,2)` percentages that must
sum to exactly 100, checked by the database.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.account import MONEY
from app.models.enums import RiskTolerance, pg_enum

PCT = Numeric(5, 2)
MIX_FIELDS = (
    "target_us_equity_pct",
    "target_intl_equity_pct",
    "target_bonds_pct",
    "target_cash_pct",
    "target_other_pct",
)


class MemberProfile(Base):
    __tablename__ = "member_profiles"
    __table_args__ = (
        CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100",
            name="ck_member_profiles_birth_year",
        ),
        CheckConstraint(
            "target_retirement_year IS NULL OR target_retirement_year BETWEEN 1900 AND 2200",
            name="ck_member_profiles_retirement_year",
        ),
        CheckConstraint(
            "birth_year IS NULL OR target_retirement_year IS NULL "
            "OR target_retirement_year > birth_year",
            name="ck_member_profiles_retire_after_birth",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    target_retirement_year: Mapped[int | None] = mapped_column(SmallInteger)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def _bounded(field: str, low: int, high: int) -> CheckConstraint:
    return CheckConstraint(
        f"{field} BETWEEN {low} AND {high}", name=f"ck_planning_assumptions_{field}"
    )


class PlanningAssumptions(Base):
    """One version of the household's assumptions. Never updated; a change is a new row."""

    __tablename__ = "planning_assumptions"
    __table_args__ = (
        _bounded("expected_real_return_bps", -1000, 2000),
        _bounded("inflation_bps", -500, 2000),
        _bounded("withdrawal_low_bps", 0, 1500),
        _bounded("withdrawal_high_bps", 0, 1500),
        _bounded("tax_deferred_withdrawal_tax_bps", 0, 6000),
        CheckConstraint(
            "withdrawal_low_bps <= withdrawal_high_bps",
            name="ck_planning_assumptions_withdrawal_band",
        ),
        CheckConstraint(
            "pre65_healthcare_annual IS NULL OR pre65_healthcare_annual >= 0",
            name="ck_planning_assumptions_healthcare",
        ),
        *(
            CheckConstraint(f"{field} BETWEEN 0 AND 100", name=f"ck_planning_assumptions_{field}")
            for field in MIX_FIELDS
        ),
        CheckConstraint(
            " + ".join(MIX_FIELDS) + " = 100", name="ck_planning_assumptions_mix_totals_100"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The row the migration inserted. The advisor says so when it states these.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Who set this version; NULL for the defaults.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    expected_real_return_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    inflation_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    withdrawal_low_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    withdrawal_high_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    #: A year of healthcare before Medicare, for early retirement. NULL: not stated.
    pre65_healthcare_annual: Mapped[Decimal | None] = mapped_column(MONEY)
    #: A flat effective rate on tax-deferred withdrawals — a simplification, stated as one.
    tax_deferred_withdrawal_tax_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(
        pg_enum(RiskTolerance, "risk_tolerance"), nullable=False
    )
    target_us_equity_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    target_intl_equity_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    target_bonds_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    target_cash_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    target_other_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
