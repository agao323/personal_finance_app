"""Shared FastAPI dependencies.

`current_user` is the single place authentication is decided. Every route that touches
household data depends on it, and its signature has not changed since ticket 012 — which
is what let Wave 2 write viewer-aware endpoints against a stand-in, needed no edits when
passkeys landed in 034, and needs none now that passkeys have gone again (047a).

**Cloudflare Access is the authentication** and the `users` table is the authorisation.
Access says which email it verified; this module decides whether that email is a member
of the household and still active. See docs/adr/0007-drop-passkeys.md for why the
passkey layer that used to sit here was removed.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models.user import User
from app.services import access
from app.services import session as sessions

logger = logging.getLogger(__name__)

#: One message for every refusal. Whether an email is unknown to this household, belongs
#: to a deactivated member, or simply carried no assertion is not a question a response
#: should answer — the log answers it, where only the operator can read it.
REFUSED = "Not signed in"


def _authenticated_email(request: Request, settings: Settings) -> str:
    """The email this request has proved, or raise 401.

    Two ways to prove it and no third: a Cloudflare Access assertion, or — only on a
    laptop, where there is no Access in front — a configured development identity.
    """
    config = access.configured()

    if config is None:
        # No Access. This is either a developer's machine or a misconfigured
        # deployment, and those must not be treated alike. `main.lifespan` already
        # refuses to boot a deployment in this state; this is the second guard, because
        # a check that exists in one place exists until someone edits that place.
        if settings.is_deployment or not settings.dev_identity_email:
            logger.warning("[auth] refused: Access is not configured and this is not local dev")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)
        return settings.dev_identity_email

    try:
        return access.verified_email(request.headers.get(access.ASSERTION_HEADER))
    except access.AccessError as error:
        # The reason goes to the log with the issuer it tried, never to the response.
        # A misconfigured team domain refuses *everyone*, owner included, and looks
        # from the outside exactly like Access working correctly — that cost hours
        # once already (ADR 0002).
        logger.warning("[auth] refused: %s (issuer %s)", error, config.issuer)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from None


def _member(db: Session, email: str) -> User:
    """The active household member with this email, or raise 401.

    Matched case-insensitively and whitespace-trimmed. Cloudflare returns whatever the
    identity provider gave it, and an allowlist that misses on `Allen@` where the row
    says `allen@` fails closed in a way that looks like a bug in Access rather than a
    bug here — the most expensive kind to diagnose.
    """
    normalised = email.strip().lower()
    user = db.execute(
        select(User)
        .where(func.lower(User.email) == normalised, User.is_active.is_(True))
        # `users.email` is unique but case-sensitively so, which leaves two rows
        # differing only in case technically possible. Ordering makes the choice
        # deterministic instead of arbitrary; 047b's migration adds a unique index on
        # `lower(email)` so the case cannot arise at all.
        .order_by(User.id)
        .limit(1)
    ).scalar_one_or_none()

    if user is None:
        # Authenticated by Access, not a member here. Logged because it is the symptom
        # of an Access policy that is broader than the household.
        logger.warning("[auth] refused: no active member for the authenticated identity")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)
    return user


def _demo_user(db: Session) -> User:
    """The identity the public demo serves to everyone.

    The demo has no Access in front — it exists to be visited — so there is nothing to
    verify and no one to identify. Until 047a this worked by accident: the demo's
    `credentials` table was empty, so the bootstrap window never closed and every
    visitor was served the seeded user. That accident died with the bootstrap window, so
    the behaviour is now stated outright.

    Safe because the demo is a separate deployment against a separate Neon project with
    synthetic data (ADR 0003), and `DemoReadOnlyMiddleware` refuses mutating verbs. It
    is emphatically **not** a way to skip authentication anywhere else: `demo_mode` is
    false by default and set only on that deployment.
    """
    user = db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.id).limit(1)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)
    return user


def current_user(request: Request, db: Annotated[Session, Depends(get_session)]) -> User:
    """The authenticated household member.

    The `users` table is the allowlist, read on every request rather than trusted from
    whenever a session was minted: deactivating a member takes effect on their very next
    request, with nothing else to revoke.
    """
    settings = get_settings()
    if settings.demo_mode:
        return _demo_user(db)
    return _member(db, _authenticated_email(request, settings))


def current_identity(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> sessions.Identity:
    """Who is signed in, and which passkey signed them in.

    Vestigial as of 047a and removed by 047b. The session cookie is **no longer an
    authentication mechanism** — honouring it here would be a way into the app that
    never passed Access, which is precisely the bypass this change closes. It survives
    only so the passkey screen keeps rendering until it is deleted.
    """
    settings = get_settings()
    cookie = request.cookies.get(sessions.COOKIE_NAME)
    if not cookie:
        return sessions.Identity(user_id=current_user(request, db).id)
    try:
        return sessions.read(cookie, settings.session_secret)
    except sessions.SessionError:
        return sessions.Identity(user_id=current_user(request, db).id)


CurrentUser = Annotated[User, Depends(current_user)]
CurrentIdentity = Annotated[sessions.Identity, Depends(current_identity)]
DbSession = Annotated[Session, Depends(get_session)]
