"""Institutions, accounts, ownership stakes, and balance snapshots.

The two load-bearing tables in the project are here. Getting them wrong means
rewriting every aggregate query later.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AccountKind, AccountSubtype, DataSource, pg_enum

#: Every money column in the schema. 2dp round-trips exactly through integer cents,
#: so the wire format needs no scale field. Never Float — see the CI guard.
MONEY = Numeric(19, 2)


class Institution(Base):
    """Banks, brokerages, lenders, 401k and HSA providers. Mostly a display grouping."""

    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    accounts: Mapped[list[Account]] = relationship(back_populates="institution")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # v1 is single-currency. Storing a field the math ignores is worse than not
        # storing it: mixed currencies would sum silently and every total would lie.
        CheckConstraint("currency = 'USD'", name="ck_accounts_currency_usd"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[AccountKind] = mapped_column(
        pg_enum(AccountKind, "account_kind"), nullable=False, index=True
    )
    subtype: Mapped[AccountSubtype] = mapped_column(
        pg_enum(AccountSubtype, "account_subtype"), nullable=False
    )
    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "data_source"), nullable=False, default=DataSource.MANUAL
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    #: Set when an account is sold, paid off, or rolled over. Net worth carries the
    #: last snapshot forward, so without this a sold car stays in net worth for ever.
    closed_at: Mapped[dt.date | None] = mapped_column(Date)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    institution: Mapped[Institution | None] = relationship(back_populates="accounts")
    stakes: Mapped[list[OwnershipStake]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[BalanceSnapshot]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class OwnershipStake(Base):
    """Effective-dated fractional ownership. ★ load-bearing.

    A stake that changes on 2027-03-01 closes the old row and opens a new one. Without
    the date range, changing a stake would silently rewrite historical net worth and
    every past point on the chart would retroactively lie.

    Every account gets an explicit 100% row at creation. There is no implicit "no row
    means fully owned" default: with two possible owners that is ambiguous, and
    removing it deletes a special case from the lookup helper rather than adding one.
    """

    __tablename__ = "ownership_stakes"
    __table_args__ = (
        CheckConstraint("percentage > 0 AND percentage <= 100", name="ck_stakes_percentage_range"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_stakes_date_order",
        ),
        Index("ix_stakes_account_effective", "account_id", "effective_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Percent, not a fraction: 50.00 means half. 2dp for the same reason money is 2dp.
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: NULL means "still in force".
    effective_to: Mapped[dt.date | None] = mapped_column(Date)

    account: Mapped[Account] = relationship(back_populates="stakes")


class BalanceSnapshot(Base):
    """★ load-bearing. Balance history is never reconstructable after the fact.

    Aggregators return *current* balances; essentially nobody backfills years of
    history. Which means history that is not captured is lost permanently. Current
    balance is derived as the latest snapshot rather than stored on `accounts`, which
    removes a whole class of consistency bug at the cost of one join.
    """

    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "as_of", name="uq_snapshot_account_date"),
        Index("ix_snapshots_account_as_of", "account_id", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: Positive for both assets and liabilities. Net worth subtracts liabilities.
    balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "data_source"), nullable=False, default=DataSource.MANUAL
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="snapshots")
