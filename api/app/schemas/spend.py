"""Spend rollups by category."""

from __future__ import annotations

import datetime as dt
import enum

from pydantic import Field

from app.schemas.common import Cents, Schema


class SpendGrouping(enum.StrEnum):
    CATEGORY = "category"
    PARENT_CATEGORY = "parent_category"


class SpendBucket(Schema):
    category_id: int | None = Field(
        default=None, description="Null is the explicit uncategorised bucket."
    )
    category_name: str
    spend_cents: Cents
    prior_period_cents: Cents | None = None
    change_cents: Cents | None = None


class SpendRead(Schema):
    """Spend for a period.

    Transfers are excluded — moving money between your own accounts is not spending,
    and if it appears as spending every number on the dashboard loses credibility.
    Uncategorised is returned as its own bucket rather than dropped: it is the prompt
    to add a rule, not noise to hide.
    """

    start: dt.date
    end: dt.date
    group_by: SpendGrouping
    total_cents: Cents
    buckets: list[SpendBucket]
    excluded_transfer_count: int = 0
