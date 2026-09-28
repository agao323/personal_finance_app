"""Liability terms: saving them for liabilities only, and reading what applies today.

The rules the database cannot hold live here: terms belong only to accounts whose `kind` is
`liability`, and a promotional rate applies through its end date and not after.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind
from app.models.liability_terms import LiabilityTerms

#: Terms last checked more than this many days ago are stale.
STALE_AFTER_DAYS = 365


class NotALiabilityError(ValueError):
    """Terms were given for an account that is not a liability."""


def require_liability(account: Account) -> None:
    if account.kind is not AccountKind.LIABILITY:
        raise NotALiabilityError(
            f"{account.name} is not a liability; only loans and cards have terms."
        )


def is_stale(terms: LiabilityTerms, today: dt.date) -> bool:
    return (today - terms.as_of).days > STALE_AFTER_DAYS


def effective_apr(terms: LiabilityTerms, today: dt.date) -> Decimal:
    """The rate that applies today: the promotional one through its end date, then the APR."""
    if terms.promo_apr is not None and terms.promo_ends_on is not None:
        if today <= terms.promo_ends_on:
            return terms.promo_apr
    return terms.apr


def get(session: Session, account_id: int) -> LiabilityTerms | None:
    return session.get(LiabilityTerms, account_id)
