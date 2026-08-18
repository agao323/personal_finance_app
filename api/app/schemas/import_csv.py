"""CSV import: preview, then commit."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.schemas.common import Cents, Schema


class ColumnMapping(Schema):
    """Maps this file's headers onto transaction fields. Header names only, never values."""

    posted_at: str
    amount: str
    merchant: str | None = None
    description: str | None = None
    external_id: str | None = None
    #: Some institutions export debits as positive. Normalised at parse time.
    invert_amount: bool | None = None


class PreviewRow(Schema):
    row_number: int
    posted_at: dt.date | None = None
    amount_cents: Cents | None = None
    merchant: str | None = None
    description: str | None = None
    external_id: str | None = None
    action: str = Field(description="create | update | skip")
    errors: list[str] = Field(default_factory=list)


class ImportPreview(Schema):
    """A dry run. Shows what *would* change, per row.

    The preview is the safety net for importing real exports — build it first, not as
    a later nicety.
    """

    account_id: int
    detected_mapping: ColumnMapping
    rows: list[PreviewRow]
    will_create: int
    will_update: int
    will_skip: int
    errors: list[str] = Field(default_factory=list)


class ImportCommitRequest(Schema):
    account_id: int
    mapping: ColumnMapping
    save_mapping_as: str | None = Field(
        default=None, description="Persist this mapping against the account for reuse."
    )
    content: str = Field(description="Raw CSV text.")


class ImportResult(Schema):
    created: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
