"""Categorisation rules. Implemented by ticket 022."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.rule import (
    RuleApplyRequest,
    RuleApplyResult,
    RuleCreate,
    RuleRead,
    RuleUpdate,
)

router = APIRouter(
    prefix="/rules",
    tags=["rules"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


@router.get("", response_model=list[RuleRead])
def list_rules(session: DbSession, user: CurrentUser) -> list[RuleRead]:
    not_implemented("022")


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(session: DbSession, user: CurrentUser, payload: RuleCreate) -> RuleRead:
    not_implemented("022")


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule(
    session: DbSession, user: CurrentUser, rule_id: int, payload: RuleUpdate
) -> RuleRead:
    not_implemented("022")


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(session: DbSession, user: CurrentUser, rule_id: int) -> Response:
    not_implemented("022")


@router.post("/apply", response_model=RuleApplyResult)
def apply_rules(
    session: DbSession, user: CurrentUser, payload: RuleApplyRequest
) -> RuleApplyResult:
    """Safe to re-run over all history. Never overwrites a manual category."""
    not_implemented("022")
