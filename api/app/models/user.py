"""Household members.

One household, two people. A member is a `users` row plus their email on the Cloudflare
Access policy — Access authenticates, this table authorises. There are no roles, no
permissions, and no credentials of our own: the passkey tables that used to live here
were removed in ticket 047b (docs/adr/0007-drop-passkeys.md).

**Deactivate, never delete.** `ownership_stakes.owner_user_id` is `ON DELETE RESTRICT`
because a stake is a historical fact; removing the user it points at would silently
rewrite past net worth.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
