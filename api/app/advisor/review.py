"""The monthly review (plan 119): which month, what it costs, and the fixed first prompt.

A review is a conversation of kind `review`, offered on the advisor screen for the month just
ended and started only when the offer is taken — **no email, no push, no scheduler**. Its first
turn carries `prompts/review.md` as context, so the model looks up the same things every month;
after that it is a conversation like any other, under the same caps, grounding and retention.
"""

from __future__ import annotations

import datetime as dt
from functools import cache
from pathlib import Path

from app.advisor.model import Usage
from app.advisor.pricing import FREE_PROVIDERS, cost_cents, display_cents

PROMPT_PATH = Path(__file__).parent / "prompts" / "review.md"

#: What one review turn uses, roughly: six lookups, so about seven model calls, most of the
#: prompt read from the cache. An estimate for the offer's "about $X", never a cap — the
#: turn's own caps still apply.
ESTIMATED_USAGE = Usage(
    input_tokens=12_000,
    cache_write_5m_tokens=10_000,
    cache_read_tokens=60_000,
    output_tokens=2_500,
)


def month_under_review(today: dt.date) -> dt.date:
    """The first day of the month before `today`'s: the month just ended."""
    last_of_prior = today.replace(day=1) - dt.timedelta(days=1)
    return last_of_prior.replace(day=1)


def _next_month(first: dt.date) -> dt.date:
    return (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def label(month: dt.date) -> str:
    """ "August 2026"."""
    return f"{month:%B %Y}"


def title(month: dt.date) -> str:
    return f"{label(month)} review"


def estimated_cost_cents(model: str, provider: str, on: dt.date) -> int | None:
    """About what a review costs on this model, in whole cents; None on a free provider."""
    if provider in FREE_PROVIDERS:
        return None
    return max(1, display_cents(cost_cents(ESTIMATED_USAGE, model, on, provider)))


@cache
def _template() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def instructions(month: dt.date) -> str:
    """The review's fixed prompt for `month`, dates filled in."""
    following = _next_month(month)
    prior = month_under_review(month)
    return _template().format(
        month_label=label(month),
        first_day=month.isoformat(),
        last_day=(following - dt.timedelta(days=1)).isoformat(),
        next_first=following.isoformat(),
        prior_first=prior.isoformat(),
        prior_last=(month - dt.timedelta(days=1)).isoformat(),
    )
