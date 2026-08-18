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
    # Required, not default_factory. Pydantic leaves a default_factory field out of
    # `required`, which makes it optional in the generated TypeScript — and then every
    # component has to guard a value the server always sends. A response field the API
    # always populates should be required in the contract that describes it.
    stale_account_ids: list[int] = Field(
        description="Accounts contributing a balance carried forward more than 90 days."
    )


class NetWorthPoint(Schema):
    as_of: dt.date
    net_worth_cents: Cents
    assets_cents: Cents
    liabilities_cents: Cents
    #: How many accounts contributed a balance carried forward past the 90-day cap.
    #:
    #: Without this a segment built from a year-old balance is indistinguishable from
    #: a measured one, and on a sparse history that is most of the line. The chart can
    #: mark those segments rather than presenting a flat stretch as if it were
    #: observed. Added in 014 at ticket 027's request; the chart wiring is 038.
    stale_account_count: int = Field(
        description="Accounts at this point using a balance carried forward past 90 days."
    )


class NetWorthSeries(Schema):
    """A time series where each point uses that date's balances and that date's stakes.

    Not today's stakes applied to old balances — that would make a stake change
    retroactively rewrite the chart.
    """

    view: ViewScope
    interval: str
    points: list[NetWorthPoint]
