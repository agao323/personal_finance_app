"""Categorisation rules. Implemented by ticket 022.

The engine itself lives in ``app.services.categorize`` — this module is the CRUD surface
over ``categorization_rules`` plus the one button that runs it.

**Patterns are validated on write, not on run.** A malformed or catastrophically
backtracking regex is rejected by `POST /rules` and `PATCH /rules/{id}` with a 422, so it
never reaches storage. Validating only at apply time would mean one bad pattern breaking
a run that has nothing else to do with it, and the error would surface far from the
person who typed it.

**Route docstrings are part of the frozen contract.** They are emitted into
`openapi.json` as operation descriptions and generated into `web/src/lib/api-types.ts`,
so editing one is a contract change. Reasoning goes in module and helper docstrings
instead — which is why this one is long and the routes below are bare.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.enums import CategorySource, MatchType
from app.models.transaction import CategorizationRule, Category, Transaction
from app.schemas.common import ErrorResponse, to_cents
from app.schemas.rule import (
    RuleApplyRequest,
    RuleApplyResult,
    RuleCreate,
    RulePreviewRequest,
    RulePreviewResult,
    RuleRead,
    RuleUpdate,
)
from app.schemas.transaction import CategoryRead, TransactionRead
from app.services import categorize


def _transaction_read(transaction: Transaction, account_name: str) -> TransactionRead:
    """The same shape `/transactions` returns, so the preview table is the same table."""
    return TransactionRead(
        id=transaction.id,
        account_id=transaction.account_id,
        account_name=account_name,
        posted_at=transaction.posted_at,
        amount_cents=to_cents(transaction.amount),
        merchant=transaction.merchant,
        description=transaction.description,
        category=(
            None
            if transaction.category is None
            else CategoryRead(
                id=transaction.category.id,
                name=transaction.category.name,
                parent_id=transaction.category.parent_id,
                kind=transaction.category.kind.value,
            )
        ),
        category_source=transaction.category_source,
        transfer_group_id=transaction.transfer_group_id,
    )


router = APIRouter(
    prefix="/rules",
    tags=["rules"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


def _to_read(rule: CategorizationRule) -> RuleRead:
    """Denormalise the category name onto the response.

    The rules screen is a list of "pattern → category" rows; without the name every row
    would need a second lookup, and the frontend would end up caching the category table
    to render a list.
    """
    return RuleRead(
        id=rule.id,
        pattern=rule.pattern,
        match_type=rule.match_type,
        category_id=rule.category_id,
        category_name=rule.category.name,
        priority=rule.priority,
    )


def _require_category(session: Session, category_id: int) -> Category:
    """422, not 404: the missing thing is in the body, not the URL.

    A 404 here would be indistinguishable from a mistyped `/rules/{rule_id}`, which is
    the kind of ambiguity that costs an afternoon.
    """
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No category with id {category_id}",
        )
    return category


def _require_rule(session: Session, rule_id: int) -> CategorizationRule:
    rule = session.get(CategorizationRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No rule with id {rule_id}"
        )
    return rule


def _validated(pattern: str, match_type: MatchType) -> None:
    """Turn an unusable pattern into a 422 rather than a 500 at apply time."""
    try:
        categorize.validate_pattern(pattern, match_type)
    except categorize.InvalidPatternError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("", response_model=list[RuleRead])
def list_rules(session: DbSession, user: CurrentUser) -> list[RuleRead]:
    rules = (
        session.execute(
            select(CategorizationRule)
            .options(joinedload(CategorizationRule.category))
            .order_by(CategorizationRule.priority, CategorizationRule.id)
        )
        .scalars()
        .all()
    )
    return [_to_read(rule) for rule in rules]


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(session: DbSession, user: CurrentUser, payload: RuleCreate) -> RuleRead:
    match_type = payload.match_type or categorize.DEFAULT_MATCH_TYPE
    _validated(payload.pattern, match_type)
    _require_category(session, payload.category_id)

    rule = CategorizationRule(
        pattern=payload.pattern,
        match_type=match_type,
        category_id=payload.category_id,
        priority=categorize.DEFAULT_PRIORITY if payload.priority is None else payload.priority,
    )
    session.add(rule)
    session.flush()
    session.refresh(rule)

    return _to_read(rule)


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule(
    session: DbSession, user: CurrentUser, rule_id: int, payload: RuleUpdate
) -> RuleRead:
    rule = _require_rule(session, rule_id)
    fields = payload.model_fields_set

    # Pattern and match type are validated together against their *resulting* pair —
    # switching an existing literal to `regex` has to re-check the pattern it will now
    # be compiled as, and changing only the pattern has to re-check it under the match
    # type already stored.
    pattern = payload.pattern if payload.pattern is not None else rule.pattern
    match_type = payload.match_type if payload.match_type is not None else rule.match_type
    if "pattern" in fields or "match_type" in fields:
        _validated(pattern, match_type)

    if payload.category_id is not None:
        _require_category(session, payload.category_id)
        rule.category_id = payload.category_id

    rule.pattern = pattern
    rule.match_type = match_type
    if payload.priority is not None:
        rule.priority = payload.priority

    session.flush()
    session.refresh(rule)

    return _to_read(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(session: DbSession, user: CurrentUser, rule_id: int) -> Response:
    rule = _require_rule(session, rule_id)

    # Transactions the rule already categorised keep their category. Clearing them would
    # make deleting one rule silently wipe history — see the "never destructive" note in
    # app/services/categorize.py.
    session.delete(rule)
    session.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=RulePreviewResult)
def preview_rule(
    session: DbSession, user: CurrentUser, payload: RulePreviewRequest
) -> RulePreviewResult:
    """Which existing transactions a pattern would match, before it is saved.

    Runs the engine's own matcher over the same subject text `apply` uses, rather than
    approximating it with a database `LIKE`. An approximation would agree with the
    engine right up until the pattern got subtle enough to actually need checking,
    which is the only time anyone looks.

    Writes nothing, and saves nothing: this is the step between typing a regex and
    finding out it re-categorised two years of history.
    """
    match_type = payload.match_type or categorize.DEFAULT_MATCH_TYPE
    _validated(payload.pattern, match_type)

    candidate = CategorizationRule(
        pattern=payload.pattern,
        match_type=match_type,
        category_id=0,
        priority=categorize.DEFAULT_PRIORITY,
    )
    compiled = categorize.compile_rules([candidate])

    rows = session.execute(
        select(Transaction, Account.name)
        .join(Account, Account.id == Transaction.account_id)
        .options(selectinload(Transaction.category))
        .order_by(Transaction.posted_at.desc(), Transaction.id.desc())
    ).all()

    matches: list[TransactionRead] = []
    match_count = 0
    already_manual = 0

    for transaction, account_name in rows:
        if categorize.first_match(compiled, categorize.subject_of(transaction)) is None:
            continue
        match_count += 1
        if transaction.category_source is CategorySource.MANUAL:
            already_manual += 1
        if len(matches) < payload.limit:
            matches.append(_transaction_read(transaction, account_name))

    return RulePreviewResult(
        match_count=match_count, already_manual=already_manual, matches=matches
    )


@router.post("/apply", response_model=RuleApplyResult)
def apply_rules(
    session: DbSession, user: CurrentUser, payload: RuleApplyRequest
) -> RuleApplyResult:
    """Safe to re-run over all history. Never overwrites a manual category."""
    try:
        result = categorize.apply_rules(
            session, only_uncategorised=bool(payload.only_uncategorised)
        )
    except categorize.RuleBudgetError as error:
        # get_session rolls back on the way out, so the half-finished run leaves no
        # trace. 422 rather than 500: the request is unprocessable because of a
        # pattern the user wrote.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return RuleApplyResult(
        examined=result.examined,
        categorised=result.categorised,
        manual_preserved=result.manual_preserved,
    )
