"""Users and their passkey credentials.

v1 ships with one row. The second is a partner: insert it, add the identity to the
Cloudflare Access policy, register a passkey. No invitations, no roles, no sharing UI.

The `users` table is also the auth allowlist — there is no separate allowlist config,
so there is no way for the two to disagree.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    credentials: Mapped[list[Credential]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Credential(Base):
    """A registered WebAuthn authenticator. Populated by ticket 034."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Authenticators report a counter that only increases. A value that goes backwards
    # suggests a cloned credential, and 034 rejects it.
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="credentials")


class WebAuthnChallenge(Base):
    """A challenge issued to a browser, waiting to be answered.

    Server-side rather than a signed token handed to the client: a challenge is only a
    challenge if it can be used once. A self-contained token is replayable until it
    expires, and "replayable for five minutes" is not the property this table exists
    to provide. Rows are deleted the moment they are consumed.
    """

    __tablename__ = "webauthn_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    #: "register" or "authenticate". A registration challenge answered with an
    #: assertion, or the reverse, is a confused-deputy shape worth refusing outright.
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Set for registration, which happens as a known user; null for authentication,
    #: where the whole point is that the server does not yet know who is signing in.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Invitation(Base):
    """A single-use, time-limited token letting a new member register their first passkey.

    It exists because the bootstrap window cannot be reopened. That window is
    "`credentials` is empty" and it shuts for good on the first registration; making it
    "empty *for this user*" would let anyone who reached the origin claim any account
    that had not registered yet.

    **It never grants a session by itself.** Redeeming it registers a passkey and
    nothing more — the passkey is what signs you in afterwards. And redemption still
    happens from behind Cloudflare Access, so the token is a second factor rather than
    the only one.

    The token is stored hashed. A readable invitation in the database is a credential
    sitting in a backup.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
