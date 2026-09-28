"""liability terms: APR, minimum payment, credit limit

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28

Ticket 112. One table, one row per liability account (enforced in the service: a CHECK cannot
see another table's `kind`). APR is NUMERIC(6,3) percent. Not effective-dated; `as_of` carries
the staleness. See `models/liability_terms.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "liability_terms",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("apr", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("minimum_payment", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column("credit_limit", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column("term_months", sa.SmallInteger(), nullable=True),
        sa.Column("maturity_on", sa.Date(), nullable=True),
        sa.Column("promo_apr", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("promo_ends_on", sa.Date(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id"),
        sa.CheckConstraint("apr >= 0 AND apr <= 100", name="ck_liability_terms_apr"),
        sa.CheckConstraint(
            "promo_apr IS NULL OR (promo_apr >= 0 AND promo_apr <= 100)",
            name="ck_liability_terms_promo_apr",
        ),
        sa.CheckConstraint(
            "(promo_apr IS NULL) = (promo_ends_on IS NULL)",
            name="ck_liability_terms_promo_has_end",
        ),
        sa.CheckConstraint(
            "minimum_payment IS NULL OR minimum_payment >= 0",
            name="ck_liability_terms_minimum_payment",
        ),
        sa.CheckConstraint(
            "credit_limit IS NULL OR credit_limit > 0", name="ck_liability_terms_credit_limit"
        ),
        sa.CheckConstraint(
            "term_months IS NULL OR term_months > 0", name="ck_liability_terms_term_months"
        ),
    )


def downgrade() -> None:
    """Drops the table. Every recorded rate, payment and limit is lost; they are retypeable."""
    op.drop_table("liability_terms")
