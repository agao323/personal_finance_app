"""CSV import. Preview is ticket 020; commit is ticket 021.

Both routes run the same planner. What the user approves in a preview is literally
the plan the commit executes, rather than a second implementation that agrees with
the first until it doesn't.

Nothing here declares extra responses or edits a docstring. The route signatures and
their descriptions are part of the frozen OpenAPI that `web/src/lib/api-types.ts` is
generated from — see tickets/README.md#wave-2-lanes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.schemas.common import ErrorResponse, to_cents
from app.schemas.import_csv import (
    ColumnMapping,
    ImportCommitRequest,
    ImportPreview,
    ImportResult,
    PreviewRow,
)
from app.services import csv_import
from app.services.csv_import import CsvFormatError, ImportPlan

router = APIRouter(prefix="/import/csv", tags=["import"], responses={422: {"model": ErrorResponse}})


def _require_account(session: DbSession, account_id: int) -> int:
    """404 for an account that does not exist, rather than a foreign key error at write."""
    exists = session.execute(
        select(Account.id).where(Account.id == account_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No account {account_id}"
        )
    return int(exists)


def _to_preview(plan: ImportPlan, mapping_source: str) -> ImportPreview:
    return ImportPreview(
        account_id=plan.account_id,
        detected_mapping=plan.mapping,
        mapping_source=mapping_source,
        rows=[
            PreviewRow(
                row_number=row.row_number,
                posted_at=row.posted_at,
                amount_cents=None if row.amount is None else to_cents(row.amount),
                merchant=row.merchant,
                description=row.description,
                external_id=row.external_id,
                action=row.action,
                errors=list(row.errors),
            )
            for row in plan.rows
        ],
        will_create=plan.count(csv_import.CREATE),
        will_update=plan.count(csv_import.UPDATE),
        will_skip=plan.count(csv_import.SKIP),
        errors=plan.errors,
    )


@router.post("/preview", response_model=ImportPreview)
async def preview_csv(
    session: DbSession,
    user: CurrentUser,
    account_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportPreview:
    """Dry run. Writes nothing — the safety net for importing real exports.

    `mapping` is an optional JSON `ColumnMapping`. Without it the account's saved
    mapping is used, falling back to detection from the header row — so the first look
    at a file needs no configuration. With it, a reader who spotted a wrong column or
    an inverted sign can see the corrected result before committing to it, which is
    the difference between a preview and a promise.

    It arrives as a JSON string because the rest of the request is multipart: a file
    upload cannot also carry a JSON body.
    """
    _require_account(session, account_id)

    supplied: ColumnMapping | None = None
    if mapping:
        try:
            supplied = ColumnMapping.model_validate_json(mapping)
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"mapping is not a valid column mapping: {error.error_count()} problems",
            ) from error

    try:
        plan, source = csv_import.preview_import(session, account_id, await file.read(), supplied)
    except CsvFormatError as exc:
        # A file with no header, no date column, or the wrong encoding has no rows to
        # show and no mapping to display, so there is no useful dry run to return.
        # Anything the parser *can* read comes back as a 200 with the problems
        # attached to the rows that have them.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return _to_preview(plan, source)


@router.post("/commit", response_model=ImportResult)
def commit_csv(session: DbSession, user: CurrentUser, payload: ImportCommitRequest) -> ImportResult:
    """Idempotent upsert. Re-importing the same file changes nothing."""
    account_id = _require_account(session, payload.account_id)

    try:
        outcome = csv_import.commit_import(
            session,
            account_id,
            payload.content,
            payload.mapping,
            payload.save_mapping_as,
        )
    except CsvFormatError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return ImportResult(
        created=outcome.created,
        updated=outcome.updated,
        skipped=outcome.skipped,
        errors=outcome.errors,
    )
