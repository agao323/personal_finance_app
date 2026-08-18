"""Accounts, ownership stakes, and balance history."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.models.enums import AccountKind, AccountSubtype, DataSource
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


class AccountUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    institution_id: int | None = None
    subtype: AccountSubtype | None = None
    closed_at: dt.date | None = None


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
    stakes: list[StakeRead] = Field(default_factory=list)


class AccountHistory(Schema):
    account_id: int
    points: list[BalanceRead]
