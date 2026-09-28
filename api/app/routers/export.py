"""Full data export.

The app must never become a place data can only go into. That is user-hostile, and it
is also insurance: a self-run database is a durability downgrade from a spreadsheet
Google was backing up, and an export you can run yourself is the escape hatch that
does not depend on the backup job working.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from app.db import Base
from app.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse
from app.schemas.export import ExportMeta, ExportRead

router = APIRouter(tags=["export"], responses={422: {"model": ErrorResponse}})


def _jsonable(value: Any) -> Any:
    """Dates as ISO strings, Decimals as strings.

    Decimal as a *string*, not a float: the export is the format someone rebuilds from
    after losing everything, and a float would quietly round the balances it exists to
    preserve. Not integer cents either — an export should be readable by a person
    opening it in a text editor, and `"1234.56"` is.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _rows(session: Session, table: Table) -> list[dict[str, Any]]:
    return [
        {column: _jsonable(value) for column, value in row._mapping.items()}
        for row in session.execute(select(table)).all()
    ]


#: Every table the export carries, and the field it lands in.
#:
#: Listed rather than derived from `Base.metadata` so that adding a table is a decision
#: someone makes rather than a silent change to the response contract. `test_export.py`
#: fails when a mapped table is missing from here, so the decision cannot be skipped.
EXPORTED = (
    "institutions",
    "accounts",
    "ownership_stakes",
    "balance_snapshots",
    "categories",
    "transactions",
    "categorization_rules",
    "import_mappings",
    "card_perks",
    "perk_redemptions",
    "users",
    "data_marker",
    "advisor_conversations",
    "advisor_turns",
    "advisor_messages",
    "advisor_tool_calls",
    "advisor_usage",
    "goals",
    "goal_accounts",
)


@router.get("/export", response_model=ExportRead)
def get_export(session: DbSession, user: CurrentUser) -> ExportRead:
    """Every row of every table, as JSON.

    Deliberately the whole dataset rather than a filtered view: the point is that nothing
    is trapped in here. Ownership stakes and their effective dates come too, because
    without them the balances alone cannot reconstruct a net worth figure.

    This is now layer two of the backup story rather than only an escape hatch — see
    [ADR 0008](../../../docs/adr/0008-local-backups.md). `make backup` writes it to disk.
    """
    tables = Base.metadata.tables
    rows = {name: _rows(session, tables[name]) for name in EXPORTED}

    return ExportRead(
        meta=ExportMeta(
            generated_at=dt.datetime.now(dt.UTC),
            account_count=len(rows["accounts"]),
            snapshot_count=len(rows["balance_snapshots"]),
            transaction_count=len(rows["transactions"]),
        ),
        **rows,
    )
