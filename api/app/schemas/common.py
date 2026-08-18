"""Shared schema primitives.

**All money crosses the wire as integer cents**, never a float and never a decimal
string. 2dp storage round-trips exactly through cents, so no scale field is needed,
and an integer cannot pick up the representation error that makes `0.1 + 0.2` equal
`0.30000000000000004`. Every such field is named `*_cents` so no caller can mistake it
for dollars. See docs/ARCHITECTURE.md#money.
"""

from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: Money on the wire. The suffix is part of the contract, not decoration.
Cents = Annotated[int, Field(description="Amount in integer cents. 1234 means $12.34.")]

#: Ownership percentage in basis points: 5000 means 50.00%, 3333 means 33.33%.
#:
#: Integer for the same reason money is. 33.33 as an IEEE-754 double is
#: 33.329999999999998, and a three-way split is a real scenario — so a percentage
#: crossing the wire as a float would not round-trip. "Never float, anywhere" holds
#: for anything that gets multiplied by a balance.
Bps = Annotated[int, Field(ge=0, le=10_000, description="Basis points. 5000 means 50.00%.")]

CENTS_PER_UNIT = 100
BPS_PER_PERCENT = 100


def to_cents(amount: Decimal) -> int:
    """Convert a stored 2dp Decimal to wire cents. Exact — no rounding happens here."""
    return int(amount.scaleb(2))


def from_cents(cents: int) -> Decimal:
    """Convert wire cents back to a 2dp Decimal."""
    return (Decimal(cents) / CENTS_PER_UNIT).quantize(Decimal("0.01"))


def to_bps(percentage: Decimal) -> int:
    """Convert a stored 2dp percentage to wire basis points. 50.00 -> 5000."""
    return int(percentage.scaleb(2))


def from_bps(bps: int) -> Decimal:
    """Convert wire basis points back to a 2dp percentage. 5000 -> 50.00."""
    return (Decimal(bps) / BPS_PER_PERCENT).quantize(Decimal("0.01"))


class Schema(BaseModel):
    """Base for every response model."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ViewScope(enum.StrEnum):
    """Whose money a figure describes.

    `mine` applies the viewer's ownership stake; `household` sums every stake. The
    only multi-user surface in the app — see ARCHITECTURE#users-and-ownership.
    """

    MINE = "mine"
    HOUSEHOLD = "household"


class Interval(enum.StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ErrorDetail(Schema):
    """One field-level problem."""

    field: str | None = Field(default=None, description="Dotted path, e.g. `body.amount_cents`.")
    message: str
    code: str | None = None


class ErrorResponse(Schema):
    """The single error shape for every non-2xx response.

    Defined once and reused so the frontend writes one error handler rather than one
    per endpoint, and so a new route cannot invent its own shape.
    """

    detail: str
    errors: list[ErrorDetail] = Field(default_factory=list)


class Page(Schema):
    """Pagination envelope metadata."""

    total: int
    limit: int
    offset: int


class DateRange(Schema):
    start: dt.date
    end: dt.date
