"""Accounts, ownership stakes, and balance history."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field, model_validator

from app.models.enums import AccountKind, AccountSubtype, AssetClass, DataSource, TaxTreatment
from app.schemas.common import Bps, Cents, Schema


class InstitutionRead(Schema):
    id: int
    name: str


class StakeRead(Schema):
    """A stake with its effective dates.

    The dates are exposed rather than just the current percentage: showing them is
    what makes effective-dating visible as a feature instead of hidden plumbing, and
    it is how a stake entered against the wrong date gets caught.
    """

    id: int
    owner_user_id: int
    owner_display_name: str
    percentage_bps: Bps
    effective_from: dt.date
    effective_to: dt.date | None = None


class StakeCreate(Schema):
    owner_user_id: int
    percentage_bps: Bps
    effective_from: dt.date


class BalanceRead(Schema):
    as_of: dt.date
    balance_cents: Cents
    source: DataSource
    is_stale: bool = Field(
        description="True when carried forward from a snapshot older than 90 days."
    )


class BalanceCreate(Schema):
    as_of: dt.date
    balance_cents: Cents
    source: DataSource | None = None


class AccountRead(Schema):
    """An account with both raw and ownership-adjusted balances.

    Both are exposed deliberately. A 50%-owned rental should visibly show the full
    value and your share — that distinction is the feature this app has and an
    off-the-shelf one does not.
    """

    id: int
    name: str
    kind: AccountKind
    subtype: AccountSubtype
    source: DataSource
    currency: str
    closed_at: dt.date | None = None
    institution: InstitutionRead | None = None
    tax_treatment: TaxTreatment = Field(
        description="How the account is taxed; the subtype's default until someone sets it."
    )

    balance_cents: Cents | None = Field(default=None, description="Raw balance, unadjusted.")
    adjusted_balance_cents: Cents | None = Field(
        default=None, description="Balance after the viewer's ownership stake."
    )
    balance_as_of: dt.date | None = None
    is_stale: bool = False
    current_stake_bps: Bps | None = None


class AccountCreate(Schema):
    name: str = Field(min_length=1, max_length=160)
    kind: AccountKind
    subtype: AccountSubtype
    institution_id: int | None = None
    institution_name: str | None = Field(
        default=None, description="Create-or-reuse an institution by name."
    )
    #: Omittable request fields are nullable rather than defaulted.
    #:
    #: openapi-typescript treats a field with a default as non-optional — correct for
    #: a response, where the server always sends it, and wrong for a request body,
    #: where it would force every caller to restate the default. `| None` says the
    #: true thing: absent means "you choose".
    source: DataSource | None = None
    #: Every account gets an explicit stake row at creation — there is no implicit
    #: "no row means fully owned" default. See ARCHITECTURE#users-and-ownership.
    owner_user_id: int | None = None
    ownership_percentage_bps: Bps | None = None
    opening_balance_cents: Cents | None = None
    opening_balance_as_of: dt.date | None = None
    tax_treatment: TaxTreatment | None = Field(
        default=None,
        description="Defaults from the subtype. A 401k with a Roth portion is two accounts.",
    )


class AccountUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    institution_id: int | None = None
    subtype: AccountSubtype | None = None
    closed_at: dt.date | None = None
    #: Credit cards only in practice. Explicit `null` clears it — absent is not zero, so a
    #: card with no fee recorded is a different state from one whose fee is $0.
    annual_fee_cents: Cents | None = Field(default=None, ge=0)
    fee_renews_on: dt.date | None = None
    tax_treatment: TaxTreatment | None = None


class DeletionPreview(Schema):
    """What removing an account would destroy.

    Counted rather than described. "All data" is a phrase people click past; "312 balance
    snapshots going back to March 2024" is one they read.
    """

    account_id: int
    name: str
    balance_snapshots: int
    transactions: int
    ownership_stakes: int
    card_perks: int
    perk_redemptions: int
    earliest_snapshot: dt.date | None = None


class AccountDelete(Schema):
    """Deleting requires naming the account.

    A destructive action reachable by one mis-click is a destructive action that happens by
    mis-click. Typing the name is the confirmation, and it is checked server-side so the
    guard does not live only in a component.
    """

    confirm_name: str


class AccountGroup(Schema):
    """Accounts of one kind with their subtotals."""

    kind: AccountKind
    accounts: list[AccountRead]
    total_cents: Cents
    adjusted_total_cents: Cents


class AccountList(Schema):
    groups: list[AccountGroup]
    total_cents: Cents
    adjusted_total_cents: Cents


class AccountDetail(AccountRead):
    stakes: list[StakeRead]


class AccountHistory(Schema):
    account_id: int
    points: list[BalanceRead]


#: A rate in thousandths of a percent: 6875 means 6.875%. APR is kept to three decimals.
PctThousandths = int


class LiabilityTermsRead(Schema):
    """What a loan or card costs to carry. Liability accounts only."""

    account_id: int
    apr_pct_thousandths: PctThousandths = Field(description="6875 means 6.875%.")
    effective_apr_pct_thousandths: PctThousandths = Field(
        description="The rate that applies today: a promotional rate through its end date."
    )
    minimum_payment_cents: Cents | None = None
    credit_limit_cents: Cents | None = Field(default=None, description="Revolving credit only.")
    term_months: int | None = None
    maturity_on: dt.date | None = None
    promo_apr_pct_thousandths: PctThousandths | None = None
    promo_ends_on: dt.date | None = Field(
        default=None, description="The promotional rate applies through this day."
    )
    as_of: dt.date = Field(description="When these were last checked.")
    stale: bool = Field(description="Last checked more than 365 days ago.")


class LiabilityTermsUpdate(Schema):
    """Every term at once. `as_of` defaults to today."""

    apr_pct_thousandths: PctThousandths = Field(ge=0, le=100_000)
    minimum_payment_cents: Cents | None = Field(default=None, ge=0)
    credit_limit_cents: Cents | None = Field(default=None, gt=0)
    term_months: int | None = Field(default=None, gt=0, le=1200)
    maturity_on: dt.date | None = None
    promo_apr_pct_thousandths: PctThousandths | None = Field(default=None, ge=0, le=100_000)
    promo_ends_on: dt.date | None = None
    as_of: dt.date | None = None

    @model_validator(mode="after")
    def _promo_has_an_end(self) -> LiabilityTermsUpdate:
        if (self.promo_apr_pct_thousandths is None) != (self.promo_ends_on is None):
            raise ValueError("A promotional rate needs its end date, and an end date its rate.")
        return self


class AllocationShare(Schema):
    asset_class: AssetClass
    percentage_bps: Bps = Field(gt=0, le=10000, description="4000 means 40.00%.")


class AllocationRow(AllocationShare):
    effective_from: dt.date
    effective_to: dt.date | None = Field(default=None, description="Null: still in force.")


class AllocationRead(Schema):
    """What an account holds by asset class today, and every allocation it has had."""

    status: Literal["recorded", "derived", "unknown", "not_applicable"] = Field(
        description="derived: follows from the subtype (cash, property, vehicles). unknown: "
        "an investment account with nothing recorded. not_applicable: a debt."
    )
    shares: list[AllocationShare] = Field(description="Totals exactly 100% when known.")
    history: list[AllocationRow]


class AllocationCreate(Schema):
    """A new allocation from a date. The one in force closes on that date."""

    effective_from: dt.date
    shares: list[AllocationShare] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _whole(self) -> AllocationCreate:
        classes = [share.asset_class for share in self.shares]
        if len(set(classes)) != len(classes):
            raise ValueError("Each asset class once.")
        total = sum(share.percentage_bps for share in self.shares)
        if total != 10000:
            whole, rest = divmod(total, 100)
            raise ValueError(
                f"An allocation must total exactly 100%; this totals {whole}.{rest:02d}%."
            )
        return self
