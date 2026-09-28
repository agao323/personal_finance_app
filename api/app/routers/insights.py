"""Insights: the findings engine's ranked observations. No model is involved.

Declared by ticket 081, implemented by 093. The engine is `services/findings.py`; see
docs/ADVISOR.md#findings.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.advisor import InsightsRead
from app.schemas.common import ErrorResponse, ViewScope
from app.services.findings import findings

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
    return InsightsRead(
        as_of=dt.date.today(),
        view=view,
        findings=findings(session, dt.date.today(), view, user.id),
    )
