"""Enumerations shared across the schema.

These ship complete rather than minimal. Adding a value to a Postgres enum later is a
migration; shipping the full set now means a connector or a new account type is code
only. See docs/ARCHITECTURE.md#account-sources.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """A Postgres enum whose labels are the member *values*, not their names.

    SQLAlchemy defaults to storing `.name`, which would put `LIQUID_ASSET` in the
    database while every JSON payload, CSV import, and API response says
    `liquid_asset`. The mismatch is invisible until something compares the two.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [m.value for m in members],
    )


class AccountKind(enum.StrEnum):
    """What a balance means for net worth.

    Liabilities are stored as **positive** balances. Net worth subtracts them. Storing
    debt as a negative number makes every aggregate ambiguous — you can never tell
    whether a sum already accounted for the sign.
    """

    LIQUID_ASSET = "liquid_asset"
    ILLIQUID_ASSET = "illiquid_asset"
    LIABILITY = "liability"


class AccountSubtype(enum.StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    CD = "cd"
    BROKERAGE = "brokerage"
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    RETIREMENT_401K = "401k"
    HSA = "hsa"
    FIVE_TWENTY_NINE = "529"
    REAL_ESTATE = "real_estate"
    VEHICLE = "vehicle"
    OTHER_ASSET = "other_asset"
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"
    AUTO_LOAN = "auto_loan"
    STUDENT_LOAN = "student_loan"
    PERSONAL_LOAN = "personal_loan"
    OTHER_LIABILITY = "other_liability"


class DataSource(enum.StrEnum):
    """Where a row came from.

    v1 implements `manual` and `csv` only. The aggregator values ship anyway so that
    adding a connector behind the SourceAdapter interface needs no migration.
    """

    MANUAL = "manual"
    CSV = "csv"
    TELLER = "teller"
    PLAID = "plaid"
    SIMPLEFIN = "simplefin"


class CategoryKind(enum.StrEnum):
    """Income, expense, or transfer.

    `transfer` is load-bearing: moving $2,000 from checking to brokerage is not
    spending, and if it shows up as spending every number on the dashboard loses
    credibility. Spend rollups filter on this.
    """

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class CategorySource(enum.StrEnum):
    """How a transaction got its category.

    Rules never overwrite `manual`. Re-running the rule set over all history must be
    safe, and a human decision outranks a pattern match.
    """

    IMPORT = "import"
    RULE = "rule"
    MANUAL = "manual"


class MatchType(enum.StrEnum):
    CONTAINS = "contains"
    EQUALS = "equals"
    STARTS_WITH = "starts_with"
    REGEX = "regex"
