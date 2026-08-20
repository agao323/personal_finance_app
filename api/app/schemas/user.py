"""Household members."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import Schema


class MemberRead(Schema):
    id: int
    email: str
    display_name: str
    is_active: bool


class MemberCreate(Schema):
    # A constrained string rather than `EmailStr`, which would pull in
    # `email-validator` to check a syntax that is not the thing that matters here.
    # What matters is that this address matches the one on the Cloudflare Access
    # policy exactly — and no format check can tell you whether it does. A typo that
    # is still a valid address passes either way and locks the person out.
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=120)


class MemberUpdate(Schema):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
