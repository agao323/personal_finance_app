"""WebAuthn ceremonies. Implemented in ticket 034.

No password schema exists anywhere, deliberately — there is no version of hand-rolled
password auth worth the time, and it is the most common way projects like this get
owned. See docs/SECURITY.md#auth.
"""

from __future__ import annotations

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
