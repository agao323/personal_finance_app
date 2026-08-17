"""Operational tables: import column mappings and the real-vs-synthetic marker."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ImportMapping(Base):
    """Remembered CSV column mapping, per account and named layout.

    Institutions each export a different shape and never change it. Persisting the
    mapping means the second import of the same export is one click.
    """

    __tablename__ = "import_mappings"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_mapping_account_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: {"posted_at": "Date", "amount": "Amount", ...} — column names only, never values.
    column_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataMarker(Base):
    """Declares whether this database holds real data.

    The synthetic seed refuses to run when `is_real` is true. That is defence in depth
    behind the real boundary — the demo's credentials cannot reach the real database —
    but it is the check that would catch a mistyped connection string before it
    overwrote a financial history.
    """

    __tablename__ = "data_marker"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_real: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
