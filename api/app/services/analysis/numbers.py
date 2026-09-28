"""The rounding site for derived figures.

**Net worth figures round in exactly one place: `services/ownership.py`**, per account, and
no analysis re-derives one. Sums and differences of stored 2dp amounts are exact and need no
rounding at all.

What is left is every figure an analysis gets by *dividing* — an average, the median of an
even count, a percentage change, a share, runway months, a projection. Those are computed
at full `Decimal` precision and rounded **once, here, at the edge**, half-up, like the rest
of the app. A second rounding site would be how two screens came to disagree by a cent.

**One stated exception: debt amortisation** (`debt.py`, ticket 115) rounds interest to cents
every month, half-up, because that is what a lender's statement does, and a schedule that
disagreed with the statement would be wrong in the way that matters.

See docs/ADVISOR.md#numbers.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
_BPS = Decimal("10000")


def quantize_money(value: Decimal) -> Decimal:
    """A derived amount, to the cent, half-up."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def ratio_bps(numerator: Decimal, denominator: Decimal) -> int | None:
    """`numerator / denominator` in basis points, half-up. `None` when there is no base."""
    if denominator == 0:
        return None
    return int((numerator * _BPS / denominator).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def change_bps(current: Decimal, prior: Decimal) -> int | None:
    """Percentage change from `prior` to `current`, in basis points. `None` from zero.

    Measured against the size of `prior`, so a change is positive when spending rose
    whether amounts are stored as outflows or inflows.
    """
    return ratio_bps(current - prior, abs(prior))


def median(values: list[Decimal]) -> Decimal:
    """The median, unrounded — the mean of the middle two for an even count."""
    if not values:
        raise ValueError("median of nothing")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def tenths(value: Decimal) -> int:
    """A quantity to tenths as a fixed-point integer: 23.45 → 235."""
    return int((value * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
