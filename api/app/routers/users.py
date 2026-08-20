"""Household members.

One household, two people. There are no roles, no permissions, and no invitation
management screen — see the "prefer boring" rule in CLAUDE.md.

**Adding a member is three systems deep and only one of them is here.** A `users` row
(this module), an entry on the Cloudflare Access policy (a dashboard edit nobody can
automate from inside the app), and their own passkey (the invitation below). Missing the
Access step means they never reach the origin at all, which looks from their side
exactly like being refused.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models.user import Credential, Invitation, User
from app.schemas.common import ErrorResponse
from app.schemas.user import (
    InvitationCreated,
    MemberCreate,
    MemberRead,
    MemberUpdate,
)

router = APIRouter(prefix="/members", tags=["members"], responses={404: {"model": ErrorResponse}})

#: Long enough to be unguessable, short enough to read aloud over a phone. It is
#: single-use and expires, and it is redeemed from behind Cloudflare Access — the
#: entropy is not the only thing standing in the way.
TOKEN_BYTES = 24

#: A window measured in days, not minutes. The person receiving it is in the same
#: household, not clicking a link in an email while it is still warm.
INVITATION_TTL = dt.timedelta(days=7)


def hash_token(token: str) -> str:
    """SHA-256 of the token. Only the hash is stored.

    Not a password hash: the token is 24 random bytes, so there is no dictionary to
    attack and nothing for bcrypt's work factor to buy. What matters is that a database
    dump — or a backup — contains no usable invitation.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _to_read(session: DbSession, user: User) -> MemberRead:
    passkeys = session.execute(
        select(func.count()).select_from(Credential).where(Credential.user_id == user.id)
    ).scalar_one()
    return MemberRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        passkey_count=int(passkeys),
    )


@router.get("", response_model=list[MemberRead])
def list_members(session: DbSession, user: CurrentUser) -> list[MemberRead]:
    """Everyone in the household, active or not."""
    members = list(session.execute(select(User).order_by(User.id)).scalars())
    return [_to_read(session, member) for member in members]


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def add_member(session: DbSession, user: CurrentUser, payload: MemberCreate) -> MemberRead:
    """Create the row. They still need an Access policy entry and a passkey."""
    existing = session.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That email is already a member")

    member = User(email=payload.email, display_name=payload.display_name, is_active=True)
    session.add(member)
    session.flush()
    return _to_read(session, member)


@router.patch("/{member_id}", response_model=MemberRead)
def update_member(
    session: DbSession, user: CurrentUser, member_id: int, payload: MemberUpdate
) -> MemberRead:
    """Activate or deactivate. There is deliberately no delete.

    `ownership_stakes.owner_user_id` is `ON DELETE RESTRICT` on purpose: a stake is a
    historical fact, and removing the user it points at would silently rewrite past net
    worth. Deactivating revokes access on the very next request — `current_user` reads
    `is_active` every time — and leaves the history intact.
    """
    member = session.get(User, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member")

    if payload.is_active is False and member.id == user.id:
        # Locking yourself out is not a thing this should help with, and with one
        # active member it would leave the household with nobody who can undo it.
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You cannot deactivate yourself")

    if payload.is_active is not None:
        member.is_active = payload.is_active
    if payload.display_name is not None:
        member.display_name = payload.display_name

    session.flush()
    return _to_read(session, member)


@router.post("/{member_id}/invitation", response_model=InvitationCreated)
def create_invitation(session: DbSession, user: CurrentUser, member_id: int) -> InvitationCreated:
    """Issue a single-use token letting this member register their first passkey.

    **The token is returned once and never again** — only its hash is stored. Losing it
    means issuing another, which is cheap; being able to read it back out of the
    database later would mean every backup carries a live credential.

    Issuing a second invitation invalidates any earlier unredeemed one, so a token that
    went to the wrong place stops working the moment you reissue.
    """
    member = session.get(User, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member")

    registered = session.execute(
        select(func.count()).select_from(Credential).where(Credential.user_id == member.id)
    ).scalar_one()
    if registered:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "That member already has a passkey. They can add devices from their own account."
            ),
        )

    for stale in session.execute(
        select(Invitation).where(Invitation.user_id == member.id, Invitation.redeemed_at.is_(None))
    ).scalars():
        session.delete(stale)

    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = dt.datetime.now(dt.UTC) + INVITATION_TTL
    session.add(Invitation(user_id=member.id, token_hash=hash_token(token), expires_at=expires_at))
    session.flush()

    return InvitationCreated(token=token, expires_at=expires_at, member_id=member.id)
