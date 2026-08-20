"""drop the passkey tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

Ticket 047b. Cloudflare Access is the authentication and this app holds no credential
of its own, so `credentials`, `webauthn_challenges` and `invitations` have nothing left
to store. See docs/adr/0007-drop-passkeys.md.

**This migration destroys data and the downgrade does not bring it back.** It recreates
the tables empty, which is the honest limit of what a downgrade can do — the rows are
gone. Anyone reversing this is re-registering passkeys from scratch, and should know
that before running it rather than after.

Nothing outside these three tables refers to them. `ownership_stakes.owner_user_id`
points at `users` and is `ON DELETE RESTRICT` on purpose (ticket 010): a stake is a
historical fact, and every net worth figure in the app depends on the user rows staying
exactly where they are. `users` is untouched here.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Children first: both reference `users`, and `invitations` and `credentials` are
    # independent of each other.
    op.drop_table("invitations")
    op.drop_table("webauthn_challenges")
    op.drop_table("credentials")

    # `users.email` is unique, but case-sensitively so — two rows differing only in
    # case were always possible and are now consequential: `deps._member` matches the
    # email Cloudflare Access verified against this column case-insensitively, and two
    # candidate rows would make which member you signed in as depend on row order.
    #
    # Created after the drops so a failure leaves the least behind.
    op.execute("UPDATE users SET email = lower(btrim(email))")
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    """Recreate the tables empty, indexes and all.

    The indexes are not decoration here: 0001, 0002 and 0003 each drop their own on the
    way down, so a table recreated without them makes *their* downgrades fail rather
    than this one. The `upgrade → downgrade → upgrade` test is what catches it.
    """
    op.drop_index("ix_users_email_lower", table_name="users")

    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("transports", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index(op.f("ix_credentials_user_id"), "credentials", ["user_id"], unique=False)

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.String(length=64), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_id"),
    )
    op.create_index(
        op.f("ix_webauthn_challenges_expires_at"),
        "webauthn_challenges",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_invitations_user_id"), "invitations", ["user_id"], unique=False)
