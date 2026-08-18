"""Account reads and writes.

Two invariants live here because they are easy to violate from a router:

**Creating an account writes its ownership stake in the same transaction.** Every
account has an explicit stake row — there is no "no row means fully owned" default, so
an account created without one is invisible to every net worth figure. Doing it in one
transaction means a failure leaves neither.

**Both raw and ownership-adjusted balances are exposed.** A 50%-owned rental should
visibly show the full value and your share. That distinction is the feature this app
has that an off-the-shelf one does not, and hiding either half wastes it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot, Institution, OwnershipStake
from app.models.enums import AccountKind, AccountSubtype, DataSource
from app.services.balances import BalanceAt, balance_in_force, record_balance
from app.services.ownership import FULL, adjust, effective_stake, household_stake

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class AccountView:
    """An account with its balance resolved for a date, both raw and adjusted."""

    account: Account
    balance: BalanceAt | None
    percentage: Decimal | None

    @property
    def adjusted(self) -> Decimal | None:
        if self.balance is None or self.percentage is None:
            return None
        return adjust(self.balance.balance, self.percentage)


def institution_for(session: Session, name: str) -> Institution:
    """Create-or-reuse by name, so importing does not spawn duplicates."""
    existing = session.execute(
        select(Institution).where(Institution.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    institution = Institution(name=name)
    session.add(institution)
    session.flush()
    return institution


def create_account(
    session: Session,
    *,
    name: str,
    kind: AccountKind,
    subtype: AccountSubtype,
    owner_user_id: int,
    institution_id: int | None = None,
    institution_name: str | None = None,
    source: DataSource | None = None,
    ownership_percentage: Decimal | None = None,
    opening_balance: Decimal | None = None,
    opening_balance_as_of: dt.date | None = None,
) -> Account:
    """Create an account, its stake, and optionally its opening balance.

    One transaction. An account without a stake row contributes to no net worth
    figure at all, so a partial success here would produce an account that exists and
    is simultaneously invisible — the worst of both.
    """
    if institution_id is None and institution_name:
        institution_id = institution_for(session, institution_name).id

    account = Account(
        institution_id=institution_id,
        name=name,
        kind=kind,
        subtype=subtype,
        source=source or DataSource.MANUAL,
        currency="USD",
    )
    session.add(account)
    session.flush()

    # The explicit stake. Not optional, not deferred.
    session.add(
        OwnershipStake(
            account_id=account.id,
            owner_user_id=owner_user_id,
            percentage=ownership_percentage or FULL,
            effective_from=opening_balance_as_of or dt.date.today(),
        )
    )

    if opening_balance is not None:
        record_balance(
            session,
            account.id,
            opening_balance_as_of or dt.date.today(),
            opening_balance,
            source or DataSource.MANUAL,
        )

    session.flush()
    return account


def view_for(
    session: Session, account: Account, as_of: dt.date, viewer_id: int | None
) -> AccountView:
    balance = balance_in_force(session, account.id, as_of)

    if viewer_id is None:
        percentage: Decimal | None = household_stake(session, account.id, as_of)
        if percentage == ZERO:
            percentage = None
    else:
        percentage = effective_stake(session, account.id, as_of, viewer_id)

    return AccountView(account=account, balance=balance, percentage=percentage)


def list_accounts(
    session: Session,
    as_of: dt.date,
    viewer_id: int | None,
    include_closed: bool = False,
) -> list[AccountView]:
    """Every account, with balances resolved for `as_of`.

    Closed accounts are excluded by default but remain requestable — the history is
    still real, and an accounts screen that silently forgets a paid-off loan is
    confusing rather than tidy.
    """
    query = select(Account).order_by(Account.kind, Account.name)
    if not include_closed:
        query = query.where((Account.closed_at.is_(None)) | (Account.closed_at > as_of))

    return [
        view_for(session, account, as_of, viewer_id) for account in session.execute(query).scalars()
    ]


def stake_history(session: Session, account_id: int) -> list[OwnershipStake]:
    """Every stake ever held, oldest first.

    The dates are the point: showing them is what makes effective-dating visible as a
    feature rather than hidden plumbing, and it is how a stake entered against the
    wrong date gets noticed.
    """
    return list(
        session.execute(
            select(OwnershipStake)
            .where(OwnershipStake.account_id == account_id)
            .order_by(OwnershipStake.effective_from, OwnershipStake.id)
        ).scalars()
    )


def snapshot_history(session: Session, account_id: int) -> list[BalanceSnapshot]:
    return list(
        session.execute(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.account_id == account_id)
            .order_by(BalanceSnapshot.as_of)
        ).scalars()
    )
