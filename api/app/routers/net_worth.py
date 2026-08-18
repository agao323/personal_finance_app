"""Net worth. Implemented by ticket 014."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse, Interval, ViewScope
from app.schemas.net_worth import NetWorthRead, NetWorthSeries

router = APIRouter(tags=["net worth"], responses={422: {"model": ErrorResponse}})


@router.get("/net-worth", response_model=NetWorthRead)
def get_net_worth(
    session: DbSession,
    user: CurrentUser,
    as_of: Annotated[dt.date | None, Query()] = None,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> NetWorthRead:
    not_implemented("014")


@router.get("/net-worth/series", response_model=NetWorthSeries)
def get_net_worth_series(
    session: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    interval: Annotated[Interval, Query()] = Interval.MONTH,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> NetWorthSeries:
    not_implemented("014")
