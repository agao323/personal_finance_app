"""WebAuthn ceremonies. Implemented in ticket 034.

No password schema exists anywhere, deliberately — there is no version of hand-rolled
password auth worth the time, and it is the most common way projects like this get
owned. See docs/SECURITY.md#auth.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.schemas.common import Schema


class RegistrationOptions(Schema):
    """Server-generated options for `navigator.credentials.create()`."""

    options: dict[str, Any]
    challenge_id: str


class RegistrationVerify(Schema):
    challenge_id: str
    credential: dict[str, Any]


class AuthenticationOptions(Schema):
    """Server-generated options for `navigator.credentials.get()`."""

    options: dict[str, Any]
    challenge_id: str


class AuthenticationVerify(Schema):
    challenge_id: str
    credential: dict[str, Any]


class SessionRead(Schema):
    user_id: int
    email: str
    display_name: str


class CredentialRead(Schema):
    """A registered authenticator, as the passkey screen needs it.

    Deliberately no public key and no credential id bytes. "Which devices can sign in
    as me" is what the screen is for and is not itself a secret; the key material is,
    and there is no reason for it to leave the database.
    """

    id: int
    created_at: dt.datetime
    last_used_at: dt.datetime | None = None
    #: True for the passkey this request's session was issued with.
    is_current: bool = False


class InvitationRedeemOptions(Schema):
    """Start registering a passkey against an invited account."""

    token: str


class InvitationRedeemVerify(Schema):
    token: str
    challenge_id: str
    credential: dict[str, Any]
