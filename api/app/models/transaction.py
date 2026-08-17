"""Categories, transactions, and the categorisation rule set."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.account import MONEY
from app.models.enums import CategoryKind, CategorySource, MatchType, pg_enum


class Category(Base):
    """Two-level taxonomy: a category may have one parent, and parents have none."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        pg_enum(CategoryKind, "category_kind"), nullable=False, index=True
    )

    parent: Mapped[Category | None] = relationship(remote_side="Category.id")


class Transaction(Base):
    """One posted transaction.

    Ingestion is **upsert, never insert**. Duplicate transactions after a re-sync are
    the single most common bug in this category of app, so the idempotency key is a
    constraint rather than a convention.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        # Partial unique index: rows without an external id (manual entries) are not
        # constrained, but any source-provided id is unique within its account.
        Index(
            "uq_transaction_account_external",
            "account_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index("ix_transactions_account_posted", "account_id", "posted_at"),
        Index("ix_transactions_posted_at", "posted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    #: The source's own identifier. NULL for manual entries.
    external_id: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[dt.date] = mapped_column(nullable=False)
    #: Signed: outflows negative, inflows positive.
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_source: Mapped[CategorySource | None] = mapped_column(
        pg_enum(CategorySource, "category_source")
    )
    #: Links the two halves of a transfer so both can be excluded from spend.
    transfer_group_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    category: Mapped[Category | None] = relationship()


class CategorizationRule(Base):
    """Ordered merchant-pattern → category rules. First match by priority wins.

    Imported categories are mediocre. Without a user-editable rule set every spending
    chart is subtly wrong and the app quietly stops being trusted.
    """

    __tablename__ = "categorization_rules"
    __table_args__ = (Index("ix_rules_priority", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[MatchType] = mapped_column(
        pg_enum(MatchType, "match_type"), nullable=False, default=MatchType.CONTAINS
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    #: Lower runs first.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    category: Mapped[Category] = relationship()
