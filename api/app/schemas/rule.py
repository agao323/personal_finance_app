"""Categorisation rules."""

from __future__ import annotations

from pydantic import Field

from app.models.enums import MatchType
from app.schemas.common import Schema
from app.schemas.transaction import TransactionRead


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


class RulePreviewRequest(Schema):
    """A pattern to try before saving it."""

    pattern: str = Field(min_length=1, max_length=255)
    match_type: MatchType | None = None
    limit: int = Field(default=20, ge=1, le=100)


class RulePreviewResult(Schema):
    """What a pattern would hit, run through the engine's own matcher.

    Computing this with a second implementation — a `LIKE` query, say — would produce a
    preview that agrees with the engine until it doesn't, which is worse than no
    preview: it is a safety net that fails silently in exactly the cases a regex is
    subtle enough to need one.

    `already_manual` counts matches the engine would leave alone because a human
    already categorised them. It is what stops the count reading as a promise the run
    will not keep.
    """

    match_count: int
    already_manual: int
    matches: list[TransactionRead]
