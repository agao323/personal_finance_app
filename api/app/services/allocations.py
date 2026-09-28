"""Tax treatment and account-level allocation (ticket 113; ADR 0013).

**Tax treatment** defaults from `subtype` — 401k and IRA tax-deferred, Roth IRA roth, brokerage
and cash taxable, HSA hsa, 529 education, property, vehicles and debts none — and is editable.
A stored NULL reads as that default, so an account inserted without one still reports one.

**Allocation** is recorded per investment account by asset class, effective-dated with half-open
ranges exactly as ownership stakes are, and **the rows in force on any date sum to exactly 100**.
A new allocation closes the rows in force on its start date and opens its own — no gap, no
overlap, and history is never rewritten. Cash, property and vehicle accounts report a
**derived** allocation from their subtype; an investment account with no rows reports
**unknown**, never a guess.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountAllocation
from app.models.enums import AccountKind, AccountSubtype, AssetClass, TaxTreatment

FULL = Decimal("100")

#: The default tax treatment per subtype. Revision 0011 backfilled with exactly this table;
#: a test holds the two together.
DEFAULT_TAX_TREATMENT: dict[AccountSubtype, TaxTreatment] = {
    AccountSubtype.CHECKING: TaxTreatment.TAXABLE,
    AccountSubtype.SAVINGS: TaxTreatment.TAXABLE,
    AccountSubtype.MONEY_MARKET: TaxTreatment.TAXABLE,
    AccountSubtype.CD: TaxTreatment.TAXABLE,
    AccountSubtype.BROKERAGE: TaxTreatment.TAXABLE,
    AccountSubtype.IRA: TaxTreatment.TAX_DEFERRED,
    AccountSubtype.RETIREMENT_401K: TaxTreatment.TAX_DEFERRED,
    AccountSubtype.ROTH_IRA: TaxTreatment.ROTH,
    AccountSubtype.HSA: TaxTreatment.HSA,
    AccountSubtype.FIVE_TWENTY_NINE: TaxTreatment.EDUCATION,
    AccountSubtype.REAL_ESTATE: TaxTreatment.NONE,
    AccountSubtype.VEHICLE: TaxTreatment.NONE,
    AccountSubtype.OTHER_ASSET: TaxTreatment.NONE,
    AccountSubtype.CREDIT_CARD: TaxTreatment.NONE,
    AccountSubtype.MORTGAGE: TaxTreatment.NONE,
    AccountSubtype.AUTO_LOAN: TaxTreatment.NONE,
    AccountSubtype.STUDENT_LOAN: TaxTreatment.NONE,
    AccountSubtype.PERSONAL_LOAN: TaxTreatment.NONE,
    AccountSubtype.OTHER_LIABILITY: TaxTreatment.NONE,
}

#: Accounts whose single asset class follows from what they are.
DERIVED_CLASS: dict[AccountSubtype, AssetClass] = {
    AccountSubtype.CHECKING: AssetClass.CASH,
    AccountSubtype.SAVINGS: AssetClass.CASH,
    AccountSubtype.MONEY_MARKET: AssetClass.CASH,
    AccountSubtype.CD: AssetClass.CASH,
    AccountSubtype.REAL_ESTATE: AssetClass.REAL_ESTATE,
    AccountSubtype.VEHICLE: AssetClass.OTHER,
}

AllocationStatus = Literal["recorded", "derived", "unknown", "not_applicable"]


class AllocationError(ValueError):
    """An allocation that cannot be recorded: not 100%, the wrong account, or out of order."""


def default_tax_treatment(subtype: AccountSubtype) -> TaxTreatment:
    return DEFAULT_TAX_TREATMENT[subtype]


def tax_treatment(account: Account) -> TaxTreatment:
    return account.tax_treatment or default_tax_treatment(account.subtype)


def takes_recorded_allocation(account: Account) -> bool:
    """Investment accounts: anything that is neither a debt nor derivable from its subtype."""
    return account.kind is not AccountKind.LIABILITY and account.subtype not in DERIVED_CLASS


def in_force(session: Session, account_id: int, on: dt.date) -> list[AccountAllocation]:
    return list(
        session.execute(
            select(AccountAllocation)
            .where(
                AccountAllocation.account_id == account_id,
                AccountAllocation.effective_from <= on,
                or_(AccountAllocation.effective_to.is_(None), AccountAllocation.effective_to > on),
            )
            .order_by(AccountAllocation.asset_class)
        ).scalars()
    )


def history(session: Session, account_id: int) -> list[AccountAllocation]:
    return list(
        session.execute(
            select(AccountAllocation)
            .where(AccountAllocation.account_id == account_id)
            .order_by(AccountAllocation.effective_from.desc(), AccountAllocation.asset_class)
        ).scalars()
    )


@dataclass(frozen=True)
class Allocation:
    status: AllocationStatus
    #: Percent per asset class, summing to exactly 100, or empty when unknown or not applicable.
    shares: dict[AssetClass, Decimal]


def allocation_for(session: Session, account: Account, on: dt.date) -> Allocation:
    if account.kind is AccountKind.LIABILITY:
        return Allocation("not_applicable", {})
    derived = DERIVED_CLASS.get(account.subtype)
    if derived is not None:
        return Allocation("derived", {derived: FULL})
    rows = in_force(session, account.id, on)
    if not rows:
        return Allocation("unknown", {})
    return Allocation("recorded", {row.asset_class: row.percentage for row in rows})


def set_allocation(
    session: Session,
    account: Account,
    shares: dict[AssetClass, Decimal],
    effective_from: dt.date,
) -> list[AccountAllocation]:
    """Close the rows in force on `effective_from` and open these, atomically."""
    if not takes_recorded_allocation(account):
        raise AllocationError(
            f"{account.name}'s allocation follows from what it is; it is not recorded."
        )
    if any(pct <= 0 for pct in shares.values()):
        raise AllocationError("Each asset class needs a share above zero; leave the rest out.")
    total = sum(shares.values(), Decimal(0))
    if total != FULL:
        raise AllocationError(f"An allocation must total exactly 100%; this totals {total}%.")
    later = session.execute(
        select(AccountAllocation.id).where(
            AccountAllocation.account_id == account.id,
            AccountAllocation.effective_from >= effective_from,
        )
    ).first()
    if later is not None:
        raise AllocationError(
            "An allocation already starts on or after that date; a new one must start later."
        )
    for row in in_force(session, account.id, effective_from):
        row.effective_to = effective_from
    created = [
        AccountAllocation(
            account_id=account.id,
            asset_class=asset_class,
            percentage=pct,
            effective_from=effective_from,
        )
        for asset_class, pct in sorted(shares.items())
    ]
    session.add_all(created)
    session.flush()
    return created


def invariant_holds(session: Session, account_id: int) -> bool:
    """Whether the rows in force sum to exactly 100 on every date any row starts or ends."""
    rows = history(session, account_id)
    boundaries = {row.effective_from for row in rows} | {
        row.effective_to for row in rows if row.effective_to is not None
    }
    for day in boundaries:
        live = in_force(session, account_id, day)
        if live and sum((row.percentage for row in live), Decimal(0)) != FULL:
            return False
    return True
