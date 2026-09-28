"""Spend analyses: two periods compared, a category month by month, where the money went.

All three build on `services/spend.py`'s own rows and totals, so the transfer, refund,
income and uncategorised rules are applied exactly as the dashboard applies them — ADR
0006's lesson is that a second statement of those rules drifts from the first.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transaction import Category
from app.services.analysis.numbers import ZERO, change_bps, median, ratio_bps
from app.services.analysis.periods import Window, like_for_like
from app.services.categorize import subject_of
from app.services.runway import has_any_transaction
from app.services.spend import BucketKey, expense_rows, spend_totals

#: A month is anomalous above this multiple of the median of the months before it…
SPIKE_MULTIPLE = Decimal("1.5")
#: …and only when it is also at least this much above it, so $12 against a $7 median is not.
SPIKE_MIN_EXCESS = Decimal("50.00")
#: Complete months the median is taken over.
TRAILING_MONTHS = 6
#: Months of data a median needs to mean anything — the same floor runway uses.
MIN_MONTHS_FOR_MEDIAN = 3


# ── comparison ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompareRow:
    category_id: int | None
    name: str
    parent_id: int | None
    a: Decimal
    b: Decimal

    @property
    def change(self) -> Decimal:
        return self.a - self.b

    @property
    def change_bps(self) -> int | None:
        return change_bps(self.a, self.b)


@dataclass(frozen=True)
class Comparison:
    a: Window
    b: Window
    #: `b` was cut to `a`'s length because `a` is still in progress.
    like_for_like: bool
    #: The whole of `b`, for context, when it was cut.
    b_full_total: Decimal | None
    rows: list[CompareRow]

    @property
    def total_a(self) -> Decimal:
        return sum((r.a for r in self.rows), ZERO)

    @property
    def total_b(self) -> Decimal:
        return sum((r.b for r in self.rows), ZERO)

    @property
    def total_change(self) -> Decimal:
        return self.total_a - self.total_b

    @property
    def total_change_bps(self) -> int | None:
        return change_bps(self.total_a, self.total_b)


def _matches(key: BucketKey, category_id: int | None) -> bool:
    return category_id is None or key[0] == category_id or key[2] == category_id


def compare(
    session: Session,
    a: Window,
    b: Window,
    by_parent: bool = False,
    category_id: int | None = None,
) -> Comparison:
    """Spend in window `a` against window `b`, per bucket.

    When `a` is still in progress, `b` is cut to the same number of days — comparing a
    partial quarter with a whole one shows a drop that is really the calendar.
    """
    cut = like_for_like(a, b)
    totals_a = spend_totals(session, a.start, a.end, by_parent)
    totals_b = spend_totals(session, cut.start, cut.end, by_parent)
    keys = [k for k in {**totals_b, **totals_a} if _matches(k, category_id)]
    rows = [
        CompareRow(
            category_id=key[0],
            name=key[1],
            parent_id=key[2],
            a=totals_a.get(key, ZERO),
            b=totals_b.get(key, ZERO),
        )
        for key in keys
    ]
    rows.sort(key=lambda r: (-r.a, -r.b, r.name))

    full = None
    if cut != b:
        full = sum(
            (
                v
                for k, v in spend_totals(session, b.start, b.end, by_parent).items()
                if _matches(k, category_id)
            ),
            ZERO,
        )
    return Comparison(a=a, b=cut, like_for_like=cut != b, b_full_total=full, rows=rows)


# ── monthly trend ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MonthPoint:
    month: dt.date
    """The first day of the month."""
    #: `None` when the month has no transactions at all: missing data, not zero spend.
    spend: Decimal | None
    #: The median of up to six complete months before this one, when three or more exist.
    trailing_median: Decimal | None
    anomaly: bool


@dataclass(frozen=True)
class Trend:
    category_id: int | None
    name: str
    months: list[MonthPoint]


def _month_starts_before(today: dt.date, count: int) -> list[dt.date]:
    """The first days of the `count` complete months before `today`'s, oldest first."""
    year, month = today.year, today.month
    starts: list[dt.date] = []
    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        starts.append(dt.date(year, month, 1))
    return starts[::-1]


def _month_end(start: dt.date) -> dt.date:
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def monthly(session: Session, today: dt.date, months: int, category_id: int | None = None) -> Trend:
    """Spend per complete month, with each month judged against the months before it.

    The current month is never included: it is partial, and a partial month always looks
    like a drop. A month with no transactions at all is reported as missing rather than
    zero — the same rule runway applies, for the same reason.
    """
    name = "All spending"
    by_parent = False
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None:
            raise ValueError(f"No category with id {category_id}.")
        name = category.name
        # A parent is measured by the parent rollup, so its children are included.
        by_parent = category.parent_id is None

    starts = _month_starts_before(today, months + TRAILING_MONTHS)
    spend: list[Decimal | None] = []
    for start in starts:
        end = _month_end(start)
        if not has_any_transaction(session, start, end):
            spend.append(None)
            continue
        totals = spend_totals(session, start, end, by_parent)
        spend.append(sum((v for k, v in totals.items() if _matches(k, category_id)), ZERO))

    points: list[MonthPoint] = []
    for index in range(TRAILING_MONTHS, len(starts)):
        prior = [v for v in spend[index - TRAILING_MONTHS : index] if v is not None]
        base = median(prior) if len(prior) >= MIN_MONTHS_FOR_MEDIAN else None
        value = spend[index]
        anomaly = (
            value is not None
            and base is not None
            and value > base * SPIKE_MULTIPLE
            and value - base >= SPIKE_MIN_EXCESS
        )
        points.append(
            MonthPoint(month=starts[index], spend=value, trailing_median=base, anomaly=anomaly)
        )
    return Trend(category_id=category_id, name=name, months=points)


# ── merchants ─────────────────────────────────────────────────────────────────

#: What a charge with no merchant and no description is grouped under.
UNKNOWN_MERCHANT = "UNKNOWN MERCHANT"
#: Payment-processor prefixes that hide the real merchant.
_PREFIXES = re.compile(r"^(SQ ?\*|TST\* ?|PAYPAL ?\*|PP\*|SP ?\*|SQSP\*|IC\*)\s*")
#: Store numbers and processor references that split one merchant into many.
_STORE_NUMBER = re.compile(r"\s*#\s*\d+\b")
_REFERENCE = re.compile(r"\*[A-Z0-9]{4,}$")
_TRAILING_DIGITS = re.compile(r"\s+\d{3,}$")
_SPACES = re.compile(r"\s+")


def normalise_merchant(subject: str) -> str:
    """One name per merchant: upper-cased, processor prefixes and store numbers removed.

    `SQ *BLUE BOTTLE #12` and `Blue Bottle 0443` are the same coffee shop, and a list of
    top merchants that shows them as two understates where the money goes.
    """
    name = _SPACES.sub(" ", subject.upper()).strip()
    name = _PREFIXES.sub("", name)
    name = _STORE_NUMBER.sub("", name)
    name = _REFERENCE.sub("", name)
    name = _TRAILING_DIGITS.sub("", name)
    name = _SPACES.sub(" ", name).strip()
    return name or UNKNOWN_MERCHANT


@dataclass(frozen=True)
class MerchantRow:
    name: str
    count: int
    spend: Decimal
    share_bps: int | None


def top_merchants(
    session: Session, window: Window, category_id: int | None = None, limit: int = 10
) -> tuple[list[MerchantRow], Decimal]:
    """Spend per merchant in the window, largest first, and the window's total.

    Refunds reduce their merchant's spend, as they reduce the category's.
    """
    groups: dict[str, tuple[int, Decimal]] = {}
    total = ZERO
    for transaction, category in expense_rows(session, window.start, window.end):
        if category_id is not None and (
            category is None or category_id not in (category.id, category.parent_id)
        ):
            continue
        amount = -transaction.amount
        total += amount
        name = normalise_merchant(subject_of(transaction))
        count, spend = groups.get(name, (0, ZERO))
        groups[name] = (count + 1, spend + amount)

    rows = [
        MerchantRow(name=name, count=count, spend=spend, share_bps=ratio_bps(spend, total))
        for name, (count, spend) in groups.items()
    ]
    rows.sort(key=lambda r: (-r.spend, r.name))
    return rows[:limit], total


@dataclass(frozen=True)
class Spike:
    category_id: int | None
    name: str
    month: dt.date
    spend: Decimal
    trailing_median: Decimal

    @property
    def excess(self) -> Decimal:
        return self.spend - self.trailing_median


def category_spikes(session: Session, today: dt.date) -> list[Spike]:
    """Leaf categories whose latest complete month is an anomaly, by `monthly`'s rule.

    Every category at once, from one set of month totals — the Insights panel asks this on
    every load, and running `monthly` per category would be a query per category per month.
    """
    starts = _month_starts_before(today, TRAILING_MONTHS + 1)
    months: list[dict[BucketKey, Decimal] | None] = []
    for start in starts:
        end = _month_end(start)
        months.append(
            spend_totals(session, start, end) if has_any_transaction(session, start, end) else None
        )
    latest = months[-1]
    if latest is None:
        return []

    spikes: list[Spike] = []
    for key, spend in latest.items():
        prior = [m.get(key, ZERO) for m in months[:-1] if m is not None]
        if len(prior) < MIN_MONTHS_FOR_MEDIAN:
            continue
        base = median(prior)
        if spend > base * SPIKE_MULTIPLE and spend - base >= SPIKE_MIN_EXCESS:
            spikes.append(
                Spike(
                    category_id=key[0],
                    name=key[1],
                    month=starts[-1],
                    spend=spend,
                    trailing_median=base,
                )
            )
    spikes.sort(key=lambda s: (-s.excess, s.name))
    return spikes
