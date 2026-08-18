"""Net worth, current and over time. Every figure is ownership-adjusted."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.models.enums import AccountKind
from app.schemas.common import Cents, Schema, ViewScope


class KindBreakdown(Schema):
    kind: AccountKind
    total_cents: Cents


class NetWorthRead(Schema):
    as_of: dt.date
    view: ViewScope
    net_worth_cents: Cents
    assets_cents: Cents
    liabilities_cents: Cents = Field(
        description="Positive. Net worth subtracts this — liabilities are stored positive."
    )
    breakdown: list[KindBreakdown]
    stale_account_ids: list[int] = Field(
        default_factory=list,
        description="Accounts contributing a balance carried forward more than 90 days.",
    )


class NetWorthPoint(Schema):
    as_of: dt.date
    net_worth_cents: Cents
    assets_cents: Cents
    liabilities_cents: Cents


class NetWorthSeries(Schema):
    """A time series where each point uses that date's balances and that date's stakes.

    Not today's stakes applied to old balances — that would make a stake change
    retroactively rewrite the chart.
    """

    view: ViewScope
    interval: str
    points: list[NetWorthPoint]
