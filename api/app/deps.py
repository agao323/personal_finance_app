"""Shared FastAPI dependencies.

``current_user`` exists now, before authentication does, so that Wave 2 can write
viewer-aware endpoints without knowing auth is missing. **Ticket 034 replaces the
implementation, not the signature** — no route should need editing when real
authentication lands.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.user import User


def current_user(session: Annotated[Session, Depends(get_session)]) -> User:
    """The authenticated household member.

    Until ticket 034 this resolves to the single seeded user — the ``users`` table is
    the auth allowlist, so "the only active user" is a coherent stand-in rather than a
    fake. Once passkeys land, this reads the session cookie and everything downstream
    is unchanged.
    """
    user = session.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.id).limit(1)
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active user configured",
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_session)]
