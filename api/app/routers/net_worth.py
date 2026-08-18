"""Net worth: current, and over time. Every figure is ownership-adjusted."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse, Interval, ViewScope, to_cents
from app.schemas.net_worth import (
    KindBreakdown,
    NetWorthPoint,
    NetWorthRead,
    NetWorthSeries,
)
from app.services.net_worth import NetWorth, net_worth, net_worth_series

router = APIRouter(tags=["net worth"], responses={422: {"model": ErrorResponse}})

#: How far back a series reaches when no `from` is given.
DEFAULT_SERIES_MONTHS = 12


def _viewer(view: ViewScope, user_id: int) -> int | None:
    """`household` means every stake; `mine` means this viewer's."""
    return None if view is ViewScope.HOUSEHOLD else user_id


def _to_read(result: NetWorth, view: ViewScope) -> NetWorthRead:
    return NetWorthRead(
        as_of=result.as_of,
        view=view,
        net_worth_cents=to_cents(result.net_worth),
        assets_cents=to_cents(result.assets),
        liabilities_cents=to_cents(result.liabilities),
        breakdown=[
            KindBreakdown(kind=kind, total_cents=to_cents(total))
            for kind, total in sorted(result.by_kind.items())
        ],
        stale_account_ids=result.stale_account_ids,
    )


@router.get("/net-worth", response_model=NetWorthRead)
def get_net_worth(
    session: DbSession,
    user: CurrentUser,
    as_of: Annotated[dt.date | None, Query()] = None,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> NetWorthRead:
    """Net worth on a date, defaulting to today.

    Accounts are excluded — never counted as zero — when they had no snapshot by
    `as_of`, when they closed on or before it, or when the viewer holds no stake in
    them. `stale_account_ids` names the accounts whose balance was carried forward
    past the 90-day cap; they are still included, because dropping them would make net
    worth silently fall on the day a snapshot aged out.
    """
    result = net_worth(session, as_of or dt.date.today(), _viewer(view, user.id))
    return _to_read(result, view)


@router.get("/net-worth/series", response_model=NetWorthSeries)
def get_net_worth_series(
    session: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    interval: Annotated[Interval, Query()] = Interval.MONTH,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> NetWorthSeries:
    """Net worth at each point in a range.

    **Carry-forward.** Each point uses the latest snapshot at or before that date, per
    account — matching `balances.balance_in_force`. Nobody records every account every
    day, so without this a chart would be mostly holes. Carry-forward is capped at 90
    days; past that the balance is still used but the point reports it via
    `stale_account_count`, so a flat stretch built from a year-old number is
    distinguishable from an observed one.

    **Each point is independent**, computed with that date's balances *and* that
    date's ownership stakes. A stake that changes in June does not rewrite May.

    **Empty and sparse history.** The series begins at the first snapshot in the
    database, never earlier: points before any balance exists are omitted rather than
    reported as zero, because a chart starting at zero would show a fortune appearing
    overnight. An empty database returns no points, and a single snapshot returns a
    single point — both are normal states on day one, not errors.
    """
    end = date_to or dt.date.today()
    start = date_from or end - dt.timedelta(days=30 * DEFAULT_SERIES_MONTHS)

    results = net_worth_series(session, start, end, interval.value, _viewer(view, user.id))

    return NetWorthSeries(
        view=view,
        interval=interval.value,
        points=[
            NetWorthPoint(
                as_of=point.as_of,
                net_worth_cents=to_cents(point.net_worth),
                assets_cents=to_cents(point.assets),
                liabilities_cents=to_cents(point.liabilities),
                stale_account_count=point.stale_count,
            )
            for point in results
        ],
    )
