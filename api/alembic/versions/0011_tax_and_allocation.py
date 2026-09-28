"""tax treatment per account, and account-level allocation

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28

Ticket 113. `accounts.tax_treatment` is added and backfilled from `subtype` with `BACKFILL`
below — the same table as `services/allocations.DEFAULT_TAX_TREATMENT`, and a test holds the two
together. The column stays nullable: NULL reads as the subtype's default, so an account inserted
without one still reports one.

`account_allocations` is effective-dated like `ownership_stakes`; the rows in force sum to
exactly 100 per account, enforced in the service. ADR 0013 has why it is per account.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tax_treatment = postgresql.ENUM(
    "taxable",
    "tax_deferred",
    "roth",
    "hsa",
    "education",
    "none",
    name="tax_treatment",
    create_type=False,
)
asset_class = postgresql.ENUM(
    "us_equity",
    "intl_equity",
    "bonds",
    "cash",
    "real_estate",
    "other",
    name="asset_class",
    create_type=False,
)

#: subtype → tax treatment. Every subtype appears; a test checks it against the service's table.
BACKFILL: dict[str, str] = {
    "checking": "taxable",
    "savings": "taxable",
    "money_market": "taxable",
    "cd": "taxable",
    "brokerage": "taxable",
    "ira": "tax_deferred",
    "401k": "tax_deferred",
    "roth_ira": "roth",
    "hsa": "hsa",
    "529": "education",
    "real_estate": "none",
    "vehicle": "none",
    "other_asset": "none",
    "credit_card": "none",
    "mortgage": "none",
    "auto_loan": "none",
    "student_loan": "none",
    "personal_loan": "none",
    "other_liability": "none",
}


def upgrade() -> None:
    tax_treatment.create(op.get_bind(), checkfirst=False)
    asset_class.create(op.get_bind(), checkfirst=False)

    op.add_column("accounts", sa.Column("tax_treatment", tax_treatment, nullable=True))
    cases = " ".join(
        f"WHEN '{subtype}' THEN '{treatment}'" for subtype, treatment in BACKFILL.items()
    )
    op.execute(
        f"UPDATE accounts SET tax_treatment = (CASE subtype::text {cases} END)::tax_treatment"
    )

    op.create_table(
        "account_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("asset_class", asset_class, nullable=False),
        sa.Column("percentage", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "percentage > 0 AND percentage <= 100", name="ck_allocations_percentage_range"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_allocations_date_order",
        ),
    )
    op.create_index(
        "ix_allocations_account_effective",
        "account_allocations",
        ["account_id", "effective_from"],
        unique=False,
    )


def downgrade() -> None:
    """Drops allocations and the tax treatment column. Both are retypeable."""
    op.drop_index("ix_allocations_account_effective", table_name="account_allocations")
    op.drop_table("account_allocations")
    op.drop_column("accounts", "tax_treatment")
    asset_class.drop(op.get_bind(), checkfirst=False)
    tax_treatment.drop(op.get_bind(), checkfirst=False)
