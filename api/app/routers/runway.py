"""Runway and burn rate — the most actionable number in the app."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse, ViewScope, to_cents
from app.schemas.runway import BurnWindow, RunwayRead
from app.services.runway import runway

router = APIRouter(tags=["runway"], responses={422: {"model": ErrorResponse}})


@router.get("/runway", response_model=RunwayRead)
def get_runway(
    session: DbSession,
    user: CurrentUser,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> RunwayRead:
    """Months of runway from liquid assets, at 3/6/12-month trailing burn.

    **Burn is gross spend excluding transfers; income is not netted.** This answers
    "how long if income stopped", which is the only version of the question worth a
    tile while income is still arriving.

    **The current month is always excluded** from the averages. It is partial by
    definition, and averaging it in makes burn look artificially low every single
    month — always in the direction that overstates how long the money lasts.

    **Months with no transaction data are skipped, not counted as zero.** Missing data
    is not a month you spent nothing, and treating it as one drags the average down.
    Months spending more than three times the window's median are excluded as
    outliers, so one house deposit does not triple the apparent burn — but only once
    there are at least three months, since with two the median is meaningless.

    **Liquid assets only.** A house is not runway and neither is a 401k you would pay
    a penalty to reach.
    """
    result = runway(session, viewer_id=None if view is ViewScope.HOUSEHOLD else user.id)

    return RunwayRead(
        liquid_assets_cents=to_cents(result.liquid_assets),
        windows=[
            BurnWindow(
                months=window.months,
                average_monthly_spend_cents=to_cents(window.average_monthly_spend),
                months_of_runway=window.months_of_runway,
            )
            for window in result.windows
        ],
        partial_month_excluded=result.partial_month_excluded,
    )
