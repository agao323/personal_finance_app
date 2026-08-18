"""CSV import. Preview is ticket 020; commit is ticket 021."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.import_csv import ImportCommitRequest, ImportPreview, ImportResult

router = APIRouter(prefix="/import/csv", tags=["import"], responses={422: {"model": ErrorResponse}})


@router.post("/preview", response_model=ImportPreview)
async def preview_csv(
    session: DbSession,
    user: CurrentUser,
    account_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
) -> ImportPreview:
    """Dry run. Writes nothing — the safety net for importing real exports."""
    not_implemented("020")


@router.post("/commit", response_model=ImportResult)
def commit_csv(session: DbSession, user: CurrentUser, payload: ImportCommitRequest) -> ImportResult:
    """Idempotent upsert. Re-importing the same file changes nothing."""
    not_implemented("021")
