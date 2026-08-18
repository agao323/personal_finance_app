"""Full data export. Implemented by ticket 017."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.export import ExportRead

router = APIRouter(tags=["export"], responses={422: {"model": ErrorResponse}})


@router.get("/export", response_model=ExportRead)
def get_export(session: DbSession, user: CurrentUser) -> ExportRead:
    not_implemented("017")
