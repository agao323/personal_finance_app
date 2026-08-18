"""Spend by category. Implemented by ticket 015."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.spend import SpendGrouping, SpendRead

router = APIRouter(tags=["spend"], responses={422: {"model": ErrorResponse}})


@router.get("/spend", response_model=SpendRead)
def get_spend(
    session: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    group_by: Annotated[SpendGrouping, Query()] = SpendGrouping.CATEGORY,
) -> SpendRead:
    not_implemented("015")
