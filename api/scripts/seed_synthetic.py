"""Generate a coherent synthetic financial picture.

This is the demo deployment's only data source and the thing that lets every frontend
ticket work without touching real money. It has to look like someone's actual
finances, not like random numbers: income and spend correlate, balances grow along
plausible curves, and the category mix resembles a household's.

**The edge cases are deliberate.** A 50%-owned rental, a mid-history stake change, a
closed account, matched transfer pairs, and uncategorised rows all exist so the
ownership maths, the carry-forward rules, and the categorisation gaps are visible on
screen rather than only in unit tests. If the demo looks tidy, it is not exercising
anything.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.account import Account, BalanceSnapshot, Institution, OwnershipStake
from app.models.enums import AccountKind, AccountSubtype, CategorySource, DataSource
from app.models.system import DataMarker
from app.models.transaction import CategorizationRule, Category, Transaction
from app.models.user import User

MONTHS = 30
DEFAULT_SEED = 20260818


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def day_in(month_start: dt.date, day: int) -> dt.date:
    """A day within a month, clamped to its length.

    A module-level function rather than a closure over the loop variable: a closure
    would capture `start` by reference, so any deferred call would silently use the
    last month rather than the one it was written beside.
    """
    last = calendar.monthrange(month_start.year, month_start.month)[1]
    return dt.date(month_start.year, month_start.month, min(day, last))


def month_starts(count: int, today: dt.date) -> list[dt.date]:
    """`count` month-start dates ending with the current month."""
    starts: list[dt.date] = []
    year, month = today.year, today.month
    for _ in range(count):
        starts.append(dt.date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(starts))


class RealDataError(RuntimeError):
    """Raised when the target database is marked as holding real data."""


def assert_not_real(session: Session) -> None:
    """Refuse to run against production.

    Defence in depth behind the real boundary — the demo's credentials cannot reach
    the real database — but this is the check that catches a mistyped connection
    string before it overwrites a financial history. It fails closed: an absent marker
    is treated as unknown, not as safe.
    """
    marker = session.execute(select(DataMarker)).scalars().first()

    if marker is None:
        raise RealDataError(
            "No data_marker row. Refusing to seed a database whose provenance is "
            "unknown — an absent marker is not a safe one."
        )
    if marker.is_real:
        raise RealDataError(
            "data_marker.is_real is true. This database holds real financial data; "
            "seeding would destroy it."
        )


def wipe(session: Session) -> None:
    """Clear generated data, leaving the schema, the marker, and seeded categories.

    Registered passkeys go too. Reseeding is a "reset this database" action, and a
    synthetic database carrying a real authenticator's credential is a confusing
    half-state: it is not what the demo deployment should serve, and locally it leaves
    the bootstrap window shut against a database that has nothing in it. It also makes
    the end-to-end run repeatable, since a fresh virtual authenticator has no
    credential to present to a stale row.
    """
    for table in (
        "transactions",
        "balance_snapshots",
        "ownership_stakes",
        "accounts",
        "institutions",
        "categorization_rules",
        "webauthn_challenges",
        "credentials",
    ):
        session.execute(text(f"DELETE FROM {table}"))
    session.execute(text("DELETE FROM users WHERE email LIKE '%@example.invalid'"))


def _categories(session: Session) -> dict[str, Category]:
    return {c.name: c for c in session.execute(select(Category)).scalars()}


def seed(session: Session, seed_value: int = DEFAULT_SEED, today: dt.date | None = None) -> None:
    """Populate the database. Same seed, same dataset, byte for byte."""
    assert_not_real(session)
    rng = random.Random(seed_value)
    today = today or dt.date.today()
    wipe(session)
    session.flush()

    categories = _categories(session)
    starts = month_starts(MONTHS, today)

    owner = session.execute(select(User).order_by(User.id)).scalars().first()
    if owner is None:
        owner = User(email="owner@example.invalid", display_name="Owner", is_active=True)
        session.add(owner)
        session.flush()

    # Two users so the Mine / Household toggle has something to show.
    partner = User(email="partner@example.invalid", display_name="Partner", is_active=True)
    session.add(partner)
    session.flush()

    institutions = {
        name: Institution(name=name)
        for name in ("Meridian Bank", "Cordova Brokerage", "Northgate Credit", "Halvorsen 401k")
    }
    session.add_all(institutions.values())
    session.flush()

    accounts = _build_accounts(session, institutions, starts, today)
    _build_stakes(session, accounts, owner, partner, starts)
    _build_snapshots(session, accounts, starts, rng)
    _build_transactions(session, accounts, categories, starts, rng, today)
    _build_rules(session, categories)
    session.flush()


def _build_accounts(
    session: Session,
    institutions: dict[str, Institution],
    starts: list[dt.date],
    today: dt.date,
) -> dict[str, Account]:
    """Every account kind, plus the two that exercise closure and part-ownership."""
    specs = [
        ("Checking", "Meridian Bank", AccountKind.LIQUID_ASSET, AccountSubtype.CHECKING, None),
        ("Savings", "Meridian Bank", AccountKind.LIQUID_ASSET, AccountSubtype.SAVINGS, None),
        (
            "Brokerage",
            "Cordova Brokerage",
            AccountKind.LIQUID_ASSET,
            AccountSubtype.BROKERAGE,
            None,
        ),
        (
            "401k",
            "Halvorsen 401k",
            AccountKind.ILLIQUID_ASSET,
            AccountSubtype.RETIREMENT_401K,
            None,
        ),
        # The home the mortgage is against. Shared with the partner on the same date
        # the mortgage is, because a household member who takes on 40% of a mortgage
        # and none of the house is not a household — it made the Household view read
        # lower than Mine, which looks like a bug in the ownership maths.
        (
            "Primary residence",
            "Meridian Bank",
            AccountKind.ILLIQUID_ASSET,
            AccountSubtype.REAL_ESTATE,
            None,
        ),
        # A different case on purpose: half of this belongs to a co-investor outside
        # the household, so even the Household view shows less than its value.
        (
            "Rental property",
            "Meridian Bank",
            AccountKind.ILLIQUID_ASSET,
            AccountSubtype.REAL_ESTATE,
            None,
        ),
        # Sold partway through: proves closed accounts leave net worth on their date
        # rather than carrying forward for ever.
        (
            "Old car",
            "Meridian Bank",
            AccountKind.ILLIQUID_ASSET,
            AccountSubtype.VEHICLE,
            starts[-8],
        ),
        (
            "Credit card",
            "Northgate Credit",
            AccountKind.LIABILITY,
            AccountSubtype.CREDIT_CARD,
            None,
        ),
        ("Mortgage", "Meridian Bank", AccountKind.LIABILITY, AccountSubtype.MORTGAGE, None),
    ]

    accounts: dict[str, Account] = {}
    for name, institution, kind, subtype, closed_at in specs:
        account = Account(
            institution_id=institutions[institution].id,
            name=name,
            kind=kind,
            subtype=subtype,
            source=DataSource.CSV if name == "Checking" else DataSource.MANUAL,
            currency="USD",
            closed_at=closed_at,
        )
        session.add(account)
        accounts[name] = account

    session.flush()
    return accounts


def _build_stakes(
    session: Session,
    accounts: dict[str, Account],
    owner: User,
    partner: User,
    starts: list[dt.date],
) -> None:
    """Every account gets an explicit stake. Two of them are deliberately interesting."""
    opened = starts[0]

    for name, account in accounts.items():
        if name == "Rental property":
            # 50% owned: the other half belongs outside the household entirely, so
            # even the Household view shows less than the property's value.
            session.add(
                OwnershipStake(
                    account_id=account.id,
                    owner_user_id=owner.id,
                    percentage=Decimal("50.00"),
                    effective_from=opened,
                )
            )
        elif name in {"Checking", "Mortgage", "Primary residence"}:
            # A mid-history stake change: sole ownership until the split date, then
            # shared. Every net worth point before that date must still read 100%.
            #
            # The residence moves with the mortgage deliberately. Sharing a debt
            # without sharing the asset it is secured against makes the partner's net
            # position negative, and Household net worth then reads *below* Mine —
            # arithmetically correct and completely misleading.
            change = starts[len(starts) // 2]
            session.add(
                OwnershipStake(
                    account_id=account.id,
                    owner_user_id=owner.id,
                    percentage=Decimal("100.00"),
                    effective_from=opened,
                    effective_to=change,
                )
            )
            session.add(
                OwnershipStake(
                    account_id=account.id,
                    owner_user_id=owner.id,
                    percentage=Decimal("60.00"),
                    effective_from=change,
                )
            )
            session.add(
                OwnershipStake(
                    account_id=account.id,
                    owner_user_id=partner.id,
                    percentage=Decimal("40.00"),
                    effective_from=change,
                )
            )
        else:
            session.add(
                OwnershipStake(
                    account_id=account.id,
                    owner_user_id=owner.id,
                    percentage=Decimal("100.00"),
                    effective_from=opened,
                )
            )


def _build_snapshots(
    session: Session,
    accounts: dict[str, Account],
    starts: list[dt.date],
    rng: random.Random,
) -> None:
    """Plausible curves: savings compound, the mortgage amortises, the card oscillates."""
    trajectories: dict[str, tuple[float, float, float]] = {
        # name: (opening, monthly drift, monthly noise)
        "Checking": (4_200, 60, 900),
        "Savings": (18_000, 750, 300),
        "Brokerage": (52_000, 1_400, 3_200),
        "401k": (96_000, 1_900, 4_100),
        "Primary residence": (505_000, 1_150, 2_400),
        "Rental property": (410_000, 900, 2_000),
        "Old car": (14_500, -240, 120),
        "Credit card": (2_400, 15, 700),
        "Mortgage": (318_000, -740, 0),
    }

    for name, account in accounts.items():
        opening, drift, noise = trajectories[name]
        value = opening

        for index, start in enumerate(starts):
            if account.closed_at is not None and start >= account.closed_at:
                break

            value = max(0.0, value + drift + rng.gauss(0, noise))
            # A deliberately sparse account: the brokerage is only recorded some
            # months, so carry-forward is visible on the chart rather than theoretical.
            if name == "Brokerage" and index % 3 == 1:
                continue

            session.add(
                BalanceSnapshot(
                    account_id=account.id,
                    as_of=start,
                    balance=money(value),
                    source=DataSource.MANUAL,
                )
            )


def _build_transactions(
    session: Session,
    accounts: dict[str, Account],
    categories: dict[str, Category],
    starts: list[dt.date],
    rng: random.Random,
    today: dt.date,
) -> None:
    """Correlated income and spend, plus transfers and a few uncategorised rows."""
    checking = accounts["Checking"]
    card = accounts["Credit card"]
    brokerage = accounts["Brokerage"]

    # Roughly 70% of take-home, which is what makes the picture coherent: income
    # around $7,400 against spend around $5,200 leaves a plausible surplus, and the
    # runway tile lands near two years rather than the eight that a token spend
    # figure would produce. A demo whose runway reads "105 months" teaches nothing.
    spend_mix = [
        ("Rent or Mortgage", 2_150, 0, 1),
        ("Groceries", 780, 140, 4),
        ("Restaurants", 420, 130, 4),
        ("Fuel", 190, 45, 2),
        ("Utilities", 310, 70, 2),
        ("Subscriptions", 96, 12, 3),
        ("Shopping", 520, 260, 3),
        ("Pharmacy", 110, 40, 1),
        ("Entertainment", 240, 95, 2),
        ("Insurance", 265, 15, 1),
        ("Car Maintenance", 145, 90, 1),
    ]

    for month_index, start in enumerate(starts):
        month = start  # bound per iteration; day_in takes it explicitly

        # Salary, rising slowly. Income is classified but never netted into burn.
        session.add(
            Transaction(
                account_id=checking.id,
                external_id=f"seed-salary-{start:%Y%m}",
                posted_at=day_in(month, 1),
                amount=money(7_400 + month_index * 22),
                merchant="Halvorsen Payroll",
                description="Monthly salary",
                category_id=categories["Salary"].id,
                category_source=CategorySource.IMPORT,
            )
        )

        for category_name, base, spread, count in spend_mix:
            for occurrence in range(count):
                session.add(
                    Transaction(
                        account_id=card.id,
                        external_id=f"seed-{category_name}-{start:%Y%m}-{occurrence}",
                        posted_at=day_in(month, 3 + occurrence * 6 + rng.randrange(0, 4)),
                        amount=money(-abs(rng.gauss(base / count, spread / count))),
                        merchant=f"{category_name} Merchant {occurrence + 1}",
                        category_id=categories[category_name].id,
                        category_source=CategorySource.RULE,
                    )
                )

        # A matched transfer pair. Both halves must vanish from spend, or a $2,000
        # investment contribution reads as $2,000 of spending.
        group = f"seed-transfer-{start:%Y%m}"
        for account, amount in ((checking, -2_000), (brokerage, 2_000)):
            session.add(
                Transaction(
                    account_id=account.id,
                    external_id=f"{group}-{account.name}",
                    posted_at=day_in(month, 2),
                    amount=money(amount),
                    merchant="Investment contribution",
                    category_id=categories["Investment Contribution"].id,
                    category_source=CategorySource.RULE,
                    transfer_group_id=group,
                )
            )

        # Uncategorised rows, shown prominently in the UI as a prompt to add a rule.
        if month_index % 4 == 0:
            session.add(
                Transaction(
                    account_id=card.id,
                    external_id=f"seed-unknown-{start:%Y%m}",
                    posted_at=day_in(month, 19),
                    amount=money(-abs(rng.gauss(70, 40))),
                    merchant=rng.choice(["SQ *UNKNOWN", "PAYPAL *XYZ", "AMZN MKTP"]),
                )
            )

        # One manual override, so category_source='manual' exists in the demo and the
        # rules engine has something it must refuse to overwrite.
        if month_index == len(starts) - 3:
            session.add(
                Transaction(
                    account_id=card.id,
                    external_id=f"seed-manual-{start:%Y%m}",
                    posted_at=day_in(month, 11),
                    amount=money(-129.99),
                    merchant="AMBIGUOUS VENDOR",
                    category_id=categories["Shopping"].id,
                    category_source=CategorySource.MANUAL,
                )
            )


def _build_rules(session: Session, categories: dict[str, Category]) -> None:
    """A starter rule set, so the rules screen is not empty in the demo."""
    rules = [
        ("Groceries Merchant", "Groceries", 10),
        ("Restaurants Merchant", "Restaurants", 20),
        ("Fuel Merchant", "Fuel", 30),
        ("Halvorsen Payroll", "Salary", 40),
        ("Investment contribution", "Investment Contribution", 50),
    ]
    for pattern, category_name, priority in rules:
        session.add(
            CategorizationRule(
                pattern=pattern,
                category_id=categories[category_name].id,
                priority=priority,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--database-url",
        default=None,
        help="defaults to DATABASE_URL from the environment",
    )
    args = parser.parse_args()

    url = args.database_url or get_settings().database_url
    engine = create_engine(url, connect_args={"prepare_threshold": None})

    with Session(engine) as session:
        try:
            seed(session, args.seed)
        except RealDataError as error:
            raise SystemExit(f"seed: refusing to run: {error}") from error
        session.commit()

    counts = {}
    with Session(engine) as session:
        for table in ("accounts", "ownership_stakes", "balance_snapshots", "transactions"):
            counts[table] = session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()

    print(f"seeded (seed={args.seed}): " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
