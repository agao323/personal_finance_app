"""The category taxonomy.

Read-only. Categories are seeded by the initial migration and are not user-editable in
v1 — what *is* user-editable is which category a transaction lands in, via the rules in
`routers/rules.py` and the manual override in `routers/transactions.py`.

The list exists because every screen that assigns a category needs to offer the
choices: the transactions screen's picker, its bulk categorise, and the rule editor.
Deriving them from `/spend` would only ever return categories that happened to have
spending in some window, which silently hides every income and transfer category and
any expense category you have not used yet.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models.transaction import Category
from app.schemas.common import ErrorResponse
from app.schemas.transaction import CategoryRead

router = APIRouter(tags=["categories"], responses={422: {"model": ErrorResponse}})


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(session: DbSession, user: CurrentUser) -> list[CategoryRead]:
    """Every category, parents before their own children.

    Ordered by `(parent_id, name)` with parents first, so a client can build a grouped
    picker by walking the list once rather than sorting a tree it has to rebuild.
    """
    rows = list(
        session.execute(
            select(Category).order_by(
                Category.parent_id.nulls_first(),
                Category.name,
            )
        ).scalars()
    )

    return [
        CategoryRead(
            id=category.id,
            name=category.name,
            parent_id=category.parent_id,
            kind=category.kind.value,
        )
        for category in rows
    ]
