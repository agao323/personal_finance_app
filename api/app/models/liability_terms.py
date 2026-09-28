"""What a loan or card costs to carry: its rate, its minimum payment, its limit.

docs/ADVISOR.md#liability-terms-wave-12-migration-in-112. One row per liability account —
**liability accounts only, enforced in the service**, because a `CHECK` cannot look at another
table's `kind`.

APR is `NUMERIC(6,3)` percent: 6.875 means 6.875%. **Not effective-dated**, unlike stakes — a
rate's history rarely changes an answer, and `as_of` carries the staleness that does: terms
last checked more than 365 days ago are stale.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.account import MONEY

APR = Numeric(6, 3)


class LiabilityTerms(Base):
    __tablename__ = "liability_terms"
    __table_args__ = (
        CheckConstraint("apr >= 0 AND apr <= 100", name="ck_liability_terms_apr"),
        CheckConstraint(
            "promo_apr IS NULL OR (promo_apr >= 0 AND promo_apr <= 100)",
            name="ck_liability_terms_promo_apr",
        ),
        CheckConstraint(
            "(promo_apr IS NULL) = (promo_ends_on IS NULL)",
            name="ck_liability_terms_promo_has_end",
        ),
        CheckConstraint(
            "minimum_payment IS NULL OR minimum_payment >= 0",
            name="ck_liability_terms_minimum_payment",
        ),
        CheckConstraint(
            "credit_limit IS NULL OR credit_limit > 0", name="ck_liability_terms_credit_limit"
        ),
        CheckConstraint(
            "term_months IS NULL OR term_months > 0", name="ck_liability_terms_term_months"
        ),
    )

    #: CASCADE: deleting the account removes its terms, as it removes everything else.
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    apr: Mapped[Decimal] = mapped_column(APR, nullable=False)
    minimum_payment: Mapped[Decimal | None] = mapped_column(MONEY)
    #: Revolving credit only.
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    term_months: Mapped[int | None] = mapped_column(SmallInteger)
    maturity_on: Mapped[dt.date | None] = mapped_column(Date)
    promo_apr: Mapped[Decimal | None] = mapped_column(APR)
    #: The promotional rate applies through this day.
    promo_ends_on: Mapped[dt.date | None] = mapped_column(Date)
    #: When these were last checked. More than 365 days ago is stale.
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
