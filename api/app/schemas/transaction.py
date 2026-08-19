"""Transactions and manual categorisation."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.models.enums import CategorySource
from app.schemas.common import Cents, Page, Schema


class CategoryRead(Schema):
    id: int
    name: str
    parent_id: int | None = None
    kind: str


class TransactionRead(Schema):
    id: int
    account_id: int
    account_name: str
    posted_at: dt.date
    amount_cents: Cents = Field(description="Signed: outflows negative, inflows positive.")
    merchant: str | None = None
    description: str | None = None
    category: CategoryRead | None = None
    category_source: CategorySource | None = None
    transfer_group_id: str | None = None


class TransactionList(Schema):
    items: list[TransactionRead]
    page: Page


class TransactionUpdate(Schema):
    """Manual re-categorisation.

    Setting a category here records ``category_source='manual'``, and re-running the
    rules engine never overwrites it. That protection is the whole reason
    ``category_source`` exists.
    """

    category_id: int | None = None


class BulkCategorise(Schema):
    transaction_ids: list[int] = Field(min_length=1)
    category_id: int | None = None


class BulkCategoriseResult(Schema):
    updated: int


class BulkTransfer(Schema):
    """Link transactions as the two sides of one transfer, or unlink them.

    `transfer_group_id` records the pairing only. What keeps a transfer out of the
    spend figures is its category's `kind`, not this field — see
    docs/ARCHITECTURE.md#transfers. Marking a pair here and leaving both sides
    categorised as expenses would link them and change no total.
    """

    transaction_ids: list[int] = Field(min_length=1)
    linked: bool = Field(
        default=True,
        description="False clears the group, leaving each transaction unpaired.",
    )


class BulkTransferResult(Schema):
    transfer_group_id: str | None = None
    updated: int
