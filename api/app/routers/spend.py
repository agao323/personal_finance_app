"""Spend by category. Powers the MTD and YTD dashboard views."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse, to_cents
from app.schemas.spend import SpendBucket, SpendGrouping, SpendRead
from app.services.spend import spend_by_category

router = APIRouter(tags=["spend"], responses={422: {"model": ErrorResponse}})


@router.get("/spend", response_model=SpendRead)
def get_spend(
    session: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    group_by: Annotated[SpendGrouping, Query()] = SpendGrouping.CATEGORY,
) -> SpendRead:
    """Spend for a period, defaulting to month-to-date.

    **Transfers and income are excluded.** Moving money between your own accounts is
    not spending, and if it appears here every number on the dashboard loses
    credibility. `excluded_transfer_count` reports how many rows that removed, so the
    exclusion is visible rather than merely true.

    **Uncategorised is a bucket, not a hole.** Rows with no category still count
    toward the total and appear under their own name — it is the prompt to add a rule,
    and dropping it would make the total quietly understate reality.

    **No ownership adjustment.** A $60 grocery charge on a jointly-owned card is $60
    of spend, not $30. The groceries were bought once. This is the one figure in the
    app where ownership deliberately does not apply — see
    docs/ARCHITECTURE.md#users-and-ownership.
    """
    end = date_to or dt.date.today()
    start = date_from or end.replace(day=1)

    summary = spend_by_category(
        session, start, end, by_parent=group_by is SpendGrouping.PARENT_CATEGORY
    )

    return SpendRead(
        start=summary.start,
        end=summary.end,
        group_by=group_by,
        total_cents=to_cents(summary.total),
        buckets=[
            SpendBucket(
                category_id=bucket.category_id,
                category_name=bucket.category_name,
                parent_id=bucket.parent_id,
                spend_cents=to_cents(bucket.spend),
                prior_period_cents=to_cents(bucket.prior_spend),
                change_cents=to_cents(bucket.change),
            )
            for bucket in summary.buckets
        ],
        excluded_transfer_count=summary.excluded_transfer_count,
    )
