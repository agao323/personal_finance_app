"""partial redemption amounts, and a card's annual fee

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26

Ticket 053. One migration for the whole cards wave, because the repo allows one in flight
at a time and splitting four columns across two would serialise five frontend tickets
behind them.

`perk_redemptions.amount` is nullable and **NULL means the full face value** — what a
one-tap mark records. A value means a partial redemption. The CHECK refuses zero: a zero
redemption is an unused period, and the absence of a row already expresses that.

`accounts.annual_fee` / `fee_renews_on` are credit-card-only in practice and deliberately
unconstrained — see the note in `models/account.py`. Absent is not zero.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("perk_redemptions", sa.Column("amount", sa.Numeric(19, 2), nullable=True))
    op.create_check_constraint(
        "ck_perk_redemptions_amount_positive",
        "perk_redemptions",
        "amount IS NULL OR amount > 0",
    )

    op.add_column("accounts", sa.Column("annual_fee", sa.Numeric(19, 2), nullable=True))
    op.add_column("accounts", sa.Column("fee_renews_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_accounts_annual_fee_positive",
        "accounts",
        "annual_fee IS NULL OR annual_fee >= 0",
    )


def downgrade() -> None:
    """Drops the columns. Any partial amounts recorded are lost — a downgrade cannot
    keep a value in a column it is removing, and every affected redemption reverts to
    meaning full face value."""
    op.drop_constraint("ck_accounts_annual_fee_positive", "accounts", type_="check")
    op.drop_column("accounts", "fee_renews_on")
    op.drop_column("accounts", "annual_fee")

    op.drop_constraint("ck_perk_redemptions_amount_positive", "perk_redemptions", type_="check")
    op.drop_column("perk_redemptions", "amount")
