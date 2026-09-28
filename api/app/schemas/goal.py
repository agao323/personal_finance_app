"""Goals over the wire. Money in integer cents; months in tenths (60 is 6.0 months)."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.models.enums import GoalKind, GoalStatus
from app.schemas.common import Cents, Schema, ViewScope

MonthsTenths = int


class GoalProgress(Schema):
    """How a goal stands today. Computed on read, never stored (ticket 111).

    One shape for every kind; the fields a kind does not use are null.
    """

    as_of: dt.date
    on_track: bool
    stale: bool = Field(description="Some figure behind this rests on a stale balance.")
    # spending_limit
    month_to_date_cents: Cents | None = None
    last_month_cents: Cents | None = None
    # emergency_fund
    runway_months_tenths: MonthsTenths | None = None
    # savings_target
    saved_cents: Cents | None = None
    remaining_cents: Cents | None = None
    monthly_needed_cents: Cents | None = Field(
        default=None, description="Still to save each month to reach the target by its date."
    )
    progress_bps: int | None = Field(
        default=None,
        description="Saved as a share of the target, or spent as a share of the limit.",
    )


class GoalRead(Schema):
    id: int
    kind: GoalKind
    name: str
    view: ViewScope = Field(description="`household` goals have no owner; `mine` are yours.")
    category_id: int | None = None
    category_name: str | None = None
    target_amount_cents: Cents | None = None
    target_months_tenths: MonthsTenths | None = None
    target_date: dt.date | None = None
    status: GoalStatus
    account_ids: list[int]
    created_at: dt.datetime
    updated_at: dt.datetime
    progress: GoalProgress | None = Field(
        default=None, description="Null until computed (ticket 111)."
    )


class GoalCreate(Schema):
    kind: GoalKind
    name: str = Field(min_length=1, max_length=120)
    view: ViewScope = Field(description="`mine` makes it yours alone; `household` shares it.")
    category_id: int | None = Field(default=None, description="spending_limit only.")
    target_amount_cents: Cents | None = Field(
        default=None, gt=0, description="savings_target total, or spending_limit per month."
    )
    target_months_tenths: MonthsTenths | None = Field(
        default=None, gt=0, le=9999, description="emergency_fund: months of spending, in tenths."
    )
    target_date: dt.date | None = None
    account_ids: list[int] = Field(
        default_factory=list, max_length=50, description="savings_target: accounts that count."
    )


class GoalUpdate(Schema):
    """Any field but the kind and whose goal it is, which define what the goal is."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = None
    target_amount_cents: Cents | None = Field(default=None, gt=0)
    target_months_tenths: MonthsTenths | None = Field(default=None, gt=0, le=9999)
    target_date: dt.date | None = None
    status: GoalStatus | None = None
    account_ids: list[int] | None = Field(default=None, max_length=50)
