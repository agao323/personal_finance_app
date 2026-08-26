"""card perks and their redemptions

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-26

Ticket 049. Perks hang off `accounts` — the `credit_card` subtype already exists, and a
separate table of cards would be a second list to keep in step with the first.

Nothing here participates in net worth. See the note in `models/card_perk.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Shipped complete. Adding a label to a Postgres enum later is its own migration, and
#: these four are what issuers actually use.
#:
#: Declared inline on the column and **not** created explicitly: `create_table` emits
#: the CREATE TYPE itself, and doing both fails with "type perk_cadence already exists".
#: This matches how 0001 declares the other six enums.
CADENCE = sa.Enum("monthly", "quarterly", "semiannual", "annual", name="perk_cadence")


def upgrade() -> None:
    op.create_table(
        "card_perks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        # NUMERIC(19,2) like every other money column. Never Float — CI guards it.
        sa.Column("value", sa.Numeric(19, 2), nullable=False),
        sa.Column("cadence", CADENCE, nullable=False),
        # The date this perk's first period began. A calendar-year credit is anchored
        # 1 January; one that resets on the cardmember year is anchored on the day the
        # card was opened. Same arithmetic either way.
        sa.Column("anchor_on", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # A perk is worth something. A zero-value perk is a note, and there is a
        # description field for those.
        sa.CheckConstraint("value > 0", name="ck_card_perks_value_positive"),
    )
    op.create_index(op.f("ix_card_perks_account_id"), "card_perks", ["account_id"], unique=False)
    op.create_index(
        "ix_card_perks_account_active", "card_perks", ["account_id", "is_active"], unique=False
    )

    op.create_table(
        "perk_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("perk_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["perk_id"], ["card_perks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Presence is the state, so a period is used exactly once. Without this,
        # double-tapping the button would record two redemptions and any count of
        # "perks used this year" would quietly overstate.
        sa.UniqueConstraint("perk_id", "period_start", name="uq_perk_redemptions_period"),
    )
    op.create_index(
        op.f("ix_perk_redemptions_perk_id"), "perk_redemptions", ["perk_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_perk_redemptions_perk_id"), table_name="perk_redemptions")
    op.drop_table("perk_redemptions")
    op.drop_index("ix_card_perks_account_active", table_name="card_perks")
    op.drop_index(op.f("ix_card_perks_account_id"), table_name="card_perks")
    op.drop_table("card_perks")
    # Postgres keeps a type until it is dropped explicitly, and leaving it behind makes
    # downgrade-then-upgrade fail with "type already exists" — which is precisely the
    # round trip `test_upgrade_downgrade_upgrade_is_clean` exercises. 0001 ends the
    # same way, for the same reason.
    op.execute("DROP TYPE IF EXISTS perk_cadence")
