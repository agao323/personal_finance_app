"""Shared FastAPI dependencies.

`current_user` is the single place authentication is decided. Every route that touches
household data depends on it, and its signature has not changed since ticket 012 —
which is what let Wave 2 write viewer-aware endpoints against a stand-in and needed no
edits when passkeys landed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models.user import Credential, User
from app.services import session as sessions


def _bootstrap_user(db: Session) -> User | None:
    """The seeded owner, but only before the first passkey exists.

    Registering a passkey requires being signed in, and signing in requires a passkey —
    so something has to open the door once. This is that: while the `credentials` table
    is empty there is no passkey anyone *could* present, and the only account is the
    one the initial migration seeded.

    The window closes the moment the first credential is stored, permanently and
    without any action. On the real deployment it is also behind Cloudflare Access the
    whole time, so "unauthenticated" here still means "already proved who they are at
    the edge".
    """
    registered = db.execute(select(func.count()).select_from(Credential)).scalar_one()
    if registered:
        return None
    return db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.id).limit(1)
    ).scalar_one_or_none()


def current_user(request: Request, db: Annotated[Session, Depends(get_session)]) -> User:
    """The authenticated household member.

    The `users` table is the allowlist: an inactive user's cookie stops working
    immediately, without anything else being revoked, because this reads `is_active`
    on every request rather than trusting what was true when the cookie was issued.
    """
    settings = get_settings()
    cookie = request.cookies.get(sessions.COOKIE_NAME)

    if cookie:
        try:
            user_id = sessions.read(cookie, settings.session_secret)
        except sessions.SessionError:
            # A bad or expired cookie is "not signed in", not "try the bootstrap" —
            # falling through would turn an expired session into a silent downgrade.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
            ) from None

        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorised")
        return user

    user = _bootstrap_user(db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_session)]
