"""What a model call cost, from its token counts and an effective-dated price table.

Cost is never stored (docs/ADVISOR.md#cost): `advisor_usage` holds token counts, and this
module turns them into cents on read. A per-call cost is a fraction of a cent, so it is
carried at full precision as a `Decimal` number of cents and rounded exactly once, by
`display_cents`, when a person is shown it. Caps compare unrounded costs.

**An unknown model costs as the most expensive known one.** A refusal fallback can be served
by a model nobody configured; pricing it at zero would let the caps be walked past, so the
error runs toward refusing early.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

#: Cents per dollar over tokens per MTok: a $/MTok rate times a token count, times this,
#: is cents.
_CENTS_PER_TOKEN_UNIT = Decimal(100) / Decimal(1_000_000)


class TokenCounts(Protocol):
    """The five token classes a call is billed in. `advisor.model.Usage` is one."""

    @property
    def input_tokens(self) -> int: ...
    @property
    def cache_write_5m_tokens(self) -> int: ...
    @property
    def cache_write_1h_tokens(self) -> int: ...
    @property
    def cache_read_tokens(self) -> int: ...
    @property
    def output_tokens(self) -> int: ...


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens, from `effective` until the next entry for the model."""

    effective: dt.date
    input: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    output: Decimal


def _price(effective: dt.date, input_: str, w5: str, w1h: str, read: str, out: str) -> Price:
    return Price(effective, Decimal(input_), Decimal(w5), Decimal(w1h), Decimal(read), Decimal(out))


#: Verified against platform.claude.com/docs/en/about-claude/pricing on 2026-09-27.
#: Entries per model are in ascending `effective` order; a price change is a new entry, not
#: an edit, so history is costed at the rate it was billed at.
_VERIFIED = dt.date(2026, 9, 27)
PRICES: dict[str, tuple[Price, ...]] = {
    "claude-opus-5": (_price(_VERIFIED, "5", "6.25", "10", "0.50", "25"),),
    "claude-opus-4-8": (_price(_VERIFIED, "5", "6.25", "10", "0.50", "25"),),
    "claude-sonnet-5": (_price(_VERIFIED, "2", "2.50", "4", "0.20", "10"),),
    "claude-haiku-4-5": (_price(_VERIFIED, "1", "1.25", "2", "0.10", "5"),),
}

#: Providers whose calls are free: the scripted fake in CI and a model on the laptop (120).
FREE_PROVIDERS = frozenset({"scripted", "local"})

_DATED = re.compile(r"-\d{8}$")


def _dearer(a: Price, b: Price) -> Price:
    return a if (a.output, a.input) >= (b.output, b.input) else b


def most_expensive() -> Price:
    latest = [entries[-1] for entries in PRICES.values()]
    worst = latest[0]
    for price in latest[1:]:
        worst = _dearer(worst, price)
    return worst


def is_priced(model: str) -> bool:
    return _DATED.sub("", model) in PRICES


def price_for(model: str, on: dt.date) -> Price:
    """The price in force for `model` on `on`. A dated snapshot id costs as its alias."""
    entries = PRICES.get(_DATED.sub("", model))
    if not entries:
        return most_expensive()
    in_force = [p for p in entries if p.effective <= on]
    # A call before the first verified entry is costed at that entry: the table starts
    # when the advisor did, so nothing real predates it.
    return in_force[-1] if in_force else entries[0]


def cost_cents(usage: TokenCounts, model: str, on: dt.date, provider: str = "anthropic") -> Decimal:
    """Cents, unrounded. Sum these; round the sum once with `display_cents`."""
    if provider in FREE_PROVIDERS:
        return Decimal(0)
    price = price_for(model, on)
    dollars_x_mtok = (
        price.input * usage.input_tokens
        + price.cache_write_5m * usage.cache_write_5m_tokens
        + price.cache_write_1h * usage.cache_write_1h_tokens
        + price.cache_read * usage.cache_read_tokens
        + price.output * usage.output_tokens
    )
    return dollars_x_mtok * _CENTS_PER_TOKEN_UNIT


def display_cents(cents: Decimal) -> int:
    """The one rounding: to whole cents, half up — the repo's rule for money."""
    return int(cents.quantize(Decimal(1), rounding=ROUND_HALF_UP))
