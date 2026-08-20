"""Household members.

One household, two people. There are no roles, no permissions, and no invitation
management screen — see the "prefer boring" rule in CLAUDE.md.

**Adding a member is two systems deep and only one of them is here.** A `users` row
(this module) and their email on the Cloudflare Access policy — a dashboard edit nobody
can automate from inside the app. Missing the Access step means they never reach the
origin at all, which looks from their side exactly like being refused.

Ticket 047b removed the third step. A new member used to need their own passkey, which
they could not register without a session and could not get a session without, so 043
built single-use invitations to break the loop. Access authenticates them now, so the
loop is gone and the invitation with it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.user import MemberCreate, MemberRead, MemberUpdate

router = APIRouter(prefix="/members", tags=["members"], responses={404: {"model": ErrorResponse}})


def _to_read(user: User) -> MemberRead:
    return MemberRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
    )


@router.get("", response_model=list[MemberRead])
def list_members(session: DbSession, user: CurrentUser) -> list[MemberRead]:
    """Everyone in the household, active or not."""
    members = list(session.execute(select(User).order_by(User.id)).scalars())
    return [_to_read(member) for member in members]


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
    return _to_read(member)


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
    return _to_read(member)
