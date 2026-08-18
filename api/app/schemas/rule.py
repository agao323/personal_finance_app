"""Categorisation rules."""

from __future__ import annotations

from pydantic import Field

from app.models.enums import MatchType
from app.schemas.common import Schema


class RuleRead(Schema):
    id: int
    pattern: str
    match_type: MatchType
    category_id: int
    category_name: str
    priority: int = Field(description="Lower runs first. First match wins.")


class RuleCreate(Schema):
    pattern: str = Field(min_length=1, max_length=255)
    match_type: MatchType | None = None
    category_id: int
    priority: int | None = None


class RuleUpdate(Schema):
    pattern: str | None = Field(default=None, min_length=1, max_length=255)
    match_type: MatchType | None = None
    category_id: int | None = None
    priority: int | None = None


class RuleApplyRequest(Schema):
    only_uncategorised: bool | None = Field(
        default=None,
        description=(
            "Re-running over all history is safe either way — manual categories are "
            "never overwritten."
        ),
    )


class RuleApplyResult(Schema):
    examined: int
    categorised: int
    manual_preserved: int
