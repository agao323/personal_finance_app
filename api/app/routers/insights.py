"""Insights: the findings engine's ranked observations. No model is involved.

Declared by ticket 081, implemented by 093. See docs/ADVISOR.md#findings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.advisor import InsightsRead
from app.schemas.common import ErrorResponse, ViewScope

router = APIRouter(tags=["insights"], responses={422: {"model": ErrorResponse}})


@router.get("/insights", response_model=InsightsRead)
def get_insights(
    session: DbSession,
    user: CurrentUser,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> InsightsRead:
    """What needs attention, ranked: severity, then money at stake, then kind.

    Spend-based findings are the same in both views — spend is never split by ownership.
    Stale evidence caps a finding at `notice` and turns its action into "update this
    balance", except for `stale_balance`, which is about exactly that.
    """
    not_implemented("093")
