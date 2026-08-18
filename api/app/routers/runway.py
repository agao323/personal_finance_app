"""Runway and burn rate. Implemented by ticket 016."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.runway import RunwayRead

router = APIRouter(tags=["runway"], responses={422: {"model": ErrorResponse}})


@router.get("/runway", response_model=RunwayRead)
def get_runway(session: DbSession, user: CurrentUser) -> RunwayRead:
    not_implemented("016")
