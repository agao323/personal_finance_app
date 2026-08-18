"""Full data export.

The app must never become a place data can only go into. That is user-hostile, and it
is also insurance: a self-run database is a durability downgrade from a spreadsheet
Google was backing up, and an export you can run yourself is the escape hatch that
does not depend on the backup job working.
"""

from __future__ import annotations

import datetime as dt
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
    return value


def _rows(session: Session, table: Table) -> list[dict[str, Any]]:
    return [
        {column: _jsonable(value) for column, value in row._mapping.items()}
        for row in session.execute(select(table)).all()
    ]


@router.get("/export", response_model=ExportRead)
def get_export(session: DbSession, user: CurrentUser) -> ExportRead:
    """Every row, as JSON.

    Deliberately the whole dataset rather than a filtered view: the point is that
    nothing is trapped in here. Ownership stakes and their effective dates come too,
    because without them the balances alone cannot reconstruct a net worth figure.
    """
    tables = {name: table for name, table in Base.metadata.tables.items()}

    accounts = _rows(session, tables["accounts"])
    snapshots = _rows(session, tables["balance_snapshots"])
    transactions = _rows(session, tables["transactions"])

    return ExportRead(
        meta=ExportMeta(
            generated_at=dt.datetime.now(dt.UTC),
            account_count=len(accounts),
            snapshot_count=len(snapshots),
            transaction_count=len(transactions),
        ),
        accounts=accounts,
        ownership_stakes=_rows(session, tables["ownership_stakes"]),
        balance_snapshots=snapshots,
        categories=_rows(session, tables["categories"]),
        transactions=transactions,
        categorization_rules=_rows(session, tables["categorization_rules"]),
    )
