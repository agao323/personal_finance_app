"""Recurring charges: what repeats, how often, what it costs a year, and what went up.

The factual half of "which subscriptions should I cancel". Whether you *use* one is yours
to say; this finds the charges, their rhythm and their price.

Detection is only as complete as the imports. A card whose export has not been imported
for two months has no recent charges to find, which `data_quality.py` reports and the
advisor is expected to say.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from typing import Literal

from sqlalchemy.orm import Session

from app.services.analysis.numbers import ZERO, change_bps, median, quantize_money
from app.services.analysis.spend_trends import normalise_merchant
from app.services.categorize import subject_of
from app.services.spend import expense_rows


@dataclass(frozen=True)
class Cadence:
    name: Literal["weekly", "fortnightly", "monthly", "quarterly", "annual"]
    #: The inclusive range of days between charges this cadence accepts.
    low: int
    high: int
    per_year: int


CADENCES = (
    Cadence("weekly", 6, 8, 52),
    Cadence("fortnightly", 13, 16, 26),
    Cadence("monthly", 27, 33, 12),
    Cadence("quarterly", 85, 95, 4),
    Cadence("annual", 355, 375, 1),
)

#: Share of intervals that must fall inside the cadence for a merchant to count.
REGULARITY = Decimal("0.75")
#: Share for `high` confidence, together with a fixed amount.
HIGH_REGULARITY = Decimal("0.90")
#: Every charge within this fraction of the median counts as a fixed amount.
FIXED_TOLERANCE = Decimal("0.10")
#: A price increase is the latest charge at least this much above the earlier median…
INCREASE_FRACTION = Decimal("0.05")
#: …and at least this many dollars above it.
INCREASE_MIN = Decimal("1.00")


@dataclass(frozen=True)
class Recurring:
    merchant: str
    category: str | None
    cadence: Cadence
    charges: int
    typical: Decimal
    fixed_amount: bool
    last_charge: dt.date
    last_amount: Decimal
    next_expected: dt.date
    #: What a year costs at the current price: the latest amount after an increase,
    #: otherwise the typical one.
    annualised: Decimal
    price_increase: Decimal | None
    price_increase_bps: int | None
    status: Literal["active", "lapsed"]
    confidence: Literal["high", "medium"]


def _lookback_start(today: dt.date, months: int) -> dt.date:
    total = today.year * 12 + (today.month - 1) - months
    return dt.date(total // 12, total % 12 + 1, 1)


def _whole_days(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cadence(interval: Decimal) -> Cadence | None:
    return next((c for c in CADENCES if c.low <= interval <= c.high), None)


def find(session: Session, today: dt.date, lookback_months: int = 12) -> list[Recurring]:
    """Every merchant charging on a regular rhythm in the lookback, active before lapsed."""
    start = _lookback_start(today, lookback_months)
    groups: dict[str, list[tuple[dt.date, Decimal, str | None]]] = {}
    for transaction, category in expense_rows(session, start, today):
        if transaction.amount >= 0:
            continue  # a refund is not a charge
        name = normalise_merchant(subject_of(transaction))
        groups.setdefault(name, []).append(
            (transaction.posted_at, -transaction.amount, category.name if category else None)
        )

    found = [r for name, rows in groups.items() if (r := _detect(name, rows, today)) is not None]
    found.sort(key=lambda r: (r.status != "active", -r.annualised, r.merchant))
    return found


def _detect(
    merchant: str, rows: list[tuple[dt.date, Decimal, str | None]], today: dt.date
) -> Recurring | None:
    rows.sort(key=lambda row: row[0])
    if len(rows) < 2:
        return None
    dates = [row[0] for row in rows]
    amounts = [row[1] for row in rows]
    intervals = [Decimal((b - a).days) for a, b in pairwise(dates)]
    interval = median(intervals)
    cadence = _cadence(interval)
    if cadence is None or (len(rows) < 3 and cadence.name != "annual"):
        return None
    inside = sum(1 for i in intervals if cadence.low <= i <= cadence.high)
    regularity = Decimal(inside) / Decimal(len(intervals))
    if regularity < REGULARITY:
        return None

    typical = quantize_money(median(amounts))
    fixed = all(abs(a - typical) <= typical * FIXED_TOLERANCE for a in amounts)

    increase: Decimal | None = None
    increase_bps: int | None = None
    if len(amounts) >= 2:
        before = median(amounts[:-1])
        latest = amounts[-1]
        if latest >= before * (1 + INCREASE_FRACTION) and latest - before >= INCREASE_MIN:
            increase = quantize_money(latest - before)
            increase_bps = change_bps(latest, before)

    step = dt.timedelta(days=_whole_days(interval))
    next_expected = dates[-1] + step
    lapsed = today > next_expected + step
    current_price = amounts[-1] if increase is not None else typical

    return Recurring(
        merchant=merchant,
        category=rows[-1][2],
        cadence=cadence,
        charges=len(rows),
        typical=typical,
        fixed_amount=fixed,
        last_charge=dates[-1],
        last_amount=amounts[-1],
        next_expected=next_expected,
        annualised=current_price * cadence.per_year,
        price_increase=increase,
        price_increase_bps=increase_bps,
        status="lapsed" if lapsed else "active",
        confidence="high" if fixed and regularity >= HIGH_REGULARITY else "medium",
    )


def active_annual_total(charges: list[Recurring]) -> Decimal:
    """What the active recurring charges cost a year, at current prices."""
    return sum((c.annualised for c in charges if c.status == "active"), ZERO)
