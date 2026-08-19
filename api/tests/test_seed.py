"""Tests for the synthetic data generator.

Two things matter here. The marker guard is the last thing standing between a
mistyped connection string and an overwritten financial history. Reproducibility is
what makes the demo a fixed artifact rather than something that quietly differs every
time it is reseeded.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.net_worth import earliest_snapshot, net_worth
from scripts.seed_synthetic import (
    DEFAULT_SEED,
    RealDataError,
    assert_not_real,
    month_starts,
    seed,
)

TODAY = dt.date(2026, 8, 18)


# ── the guard ─────────────────────────────────────────────────────────────────


def test_refuses_a_database_marked_real(db_session: Session) -> None:
    """The check that catches a mistyped connection string before it destroys data."""
    db_session.execute(text("UPDATE data_marker SET is_real = true"))

    with pytest.raises(RealDataError, match="real financial data"):
        assert_not_real(db_session)


def test_refuses_a_database_with_no_marker(db_session: Session) -> None:
    """Fails closed: an absent marker is unknown provenance, not a safe one."""
    db_session.execute(text("DELETE FROM data_marker"))

    with pytest.raises(RealDataError, match="provenance is unknown"):
        assert_not_real(db_session)


def test_allows_a_synthetic_database(db_session: Session) -> None:
    assert_not_real(db_session)  # marker seeded false by the migration


def test_seed_itself_refuses_a_real_database(db_session: Session) -> None:
    """The guard is inside seed(), not merely available to callers."""
    db_session.execute(text("UPDATE data_marker SET is_real = true"))

    with pytest.raises(RealDataError):
        seed(db_session, today=TODAY)


# ── reproducibility ───────────────────────────────────────────────────────────


def _fingerprint(session: Session) -> list[tuple[str, str]]:
    rows = session.execute(
        text(
            "SELECT a.name, s.as_of::text, s.balance::text "
            "FROM balance_snapshots s JOIN accounts a ON a.id = s.account_id "
            "ORDER BY a.name, s.as_of"
        )
    ).all()
    return [(f"{n}|{d}", b) for n, d, b in rows]


def test_the_same_seed_reproduces_the_same_dataset(db_session: Session) -> None:
    """A demo that differs on every reseed is not a fixed artifact."""
    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)
    first = _fingerprint(db_session)

    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)
    second = _fingerprint(db_session)

    assert first == second
    assert len(first) > 100


def test_a_different_seed_produces_a_different_dataset(db_session: Session) -> None:
    seed(db_session, seed_value=1, today=TODAY)
    first = _fingerprint(db_session)

    seed(db_session, seed_value=2, today=TODAY)

    assert first != _fingerprint(db_session)


def test_reseeding_replaces_rather_than_accumulates(db_session: Session) -> None:
    seed(db_session, today=TODAY)
    count = db_session.execute(text("SELECT count(*) FROM accounts")).scalar_one()

    seed(db_session, today=TODAY)

    assert db_session.execute(text("SELECT count(*) FROM accounts")).scalar_one() == count


# ── the deliberate edge cases ─────────────────────────────────────────────────


def test_seeds_two_users_so_the_toggle_has_something_to_show(db_session: Session) -> None:
    seed(db_session, today=TODAY)

    assert db_session.execute(text("SELECT count(*) FROM users")).scalar_one() >= 2


def test_seeds_a_part_owned_asset(db_session: Session) -> None:
    """A 50%-owned rental: even Household shows less than the property's value."""
    seed(db_session, today=TODAY)

    percentage = db_session.execute(
        text(
            "SELECT s.percentage FROM ownership_stakes s "
            "JOIN accounts a ON a.id = s.account_id WHERE a.name = 'Rental property'"
        )
    ).scalar_one()

    assert percentage == Decimal("50.00")


def test_seeds_a_mid_history_stake_change(db_session: Session) -> None:
    """The case that proves a stake change does not rewrite the past."""
    seed(db_session, today=TODAY)

    closed = db_session.execute(
        text(
            "SELECT count(*) FROM ownership_stakes s JOIN accounts a ON a.id = s.account_id "
            "WHERE a.name = 'Checking' AND s.effective_to IS NOT NULL"
        )
    ).scalar_one()

    assert closed >= 1


def test_seeds_a_closed_account(db_session: Session) -> None:
    seed(db_session, today=TODAY)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM accounts WHERE closed_at IS NOT NULL")
        ).scalar_one()
        >= 1
    )


def test_seeds_matched_transfer_pairs(db_session: Session) -> None:
    """Both halves must exist, or transfer exclusion has nothing to exclude."""
    seed(db_session, today=TODAY)

    pairs = db_session.execute(
        text(
            "SELECT transfer_group_id, count(*) FROM transactions "
            "WHERE transfer_group_id IS NOT NULL GROUP BY transfer_group_id"
        )
    ).all()

    assert pairs
    assert all(count == 2 for _, count in pairs)


def test_seeds_uncategorised_transactions(db_session: Session) -> None:
    """The UI surfaces these prominently as a prompt to add a rule."""
    seed(db_session, today=TODAY)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM transactions WHERE category_id IS NULL")
        ).scalar_one()
        >= 1
    )


def test_seeds_a_manual_override(db_session: Session) -> None:
    """So the rules engine has something it must refuse to overwrite."""
    seed(db_session, today=TODAY)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM transactions WHERE category_source = 'manual'")
        ).scalar_one()
        >= 1
    )


def test_seeds_a_sparse_account_so_carry_forward_is_visible(db_session: Session) -> None:
    """The brokerage is recorded some months only — carry-forward on screen, not in theory."""
    seed(db_session, today=TODAY)

    counts: dict[str, int] = {
        name: count
        for name, count in db_session.execute(
            text(
                "SELECT a.name, count(s.id) FROM accounts a "
                "LEFT JOIN balance_snapshots s ON s.account_id = a.id GROUP BY a.name"
            )
        ).all()
    }

    assert counts["Brokerage"] < counts["Savings"]


def test_seeds_every_account_kind(db_session: Session) -> None:
    seed(db_session, today=TODAY)

    kinds = set(db_session.execute(text("SELECT DISTINCT kind FROM accounts")).scalars())
    assert kinds == {"liquid_asset", "illiquid_asset", "liability"}


def test_seeds_a_starter_rule_set(db_session: Session) -> None:
    """So the rules screen is not empty in the demo."""
    seed(db_session, today=TODAY)

    assert db_session.execute(text("SELECT count(*) FROM categorization_rules")).scalar_one() >= 1


def test_every_account_has_an_explicit_stake(db_session: Session) -> None:
    """The invariant the whole ownership design rests on."""
    seed(db_session, today=TODAY)

    orphaned = db_session.execute(
        text(
            "SELECT count(*) FROM accounts a WHERE NOT EXISTS "
            "(SELECT 1 FROM ownership_stakes s WHERE s.account_id = a.id)"
        )
    ).scalar_one()

    assert orphaned == 0


def test_liabilities_are_stored_positive(db_session: Session) -> None:
    seed(db_session, today=TODAY)

    negative = db_session.execute(
        text(
            "SELECT count(*) FROM balance_snapshots s JOIN accounts a ON a.id = s.account_id "
            "WHERE a.kind = 'liability' AND s.balance < 0"
        )
    ).scalar_one()

    assert negative == 0


def test_month_starts_ends_with_the_current_month(db_session: Session) -> None:
    starts = month_starts(3, TODAY)

    assert starts == [dt.date(2026, 6, 1), dt.date(2026, 7, 1), dt.date(2026, 8, 1)]


def test_household_net_worth_is_never_below_mine(db_session: Session) -> None:
    """The invariant that makes the Mine / Household toggle legible.

    Household sums every stake and Mine is a subset of them, so household can never be
    the smaller number — but it *was*, by $118k, because the seeded partner took 40% of
    a mortgage and no share of the house it was against. The maths was right and the
    picture was nonsense, which is the worst combination to ship on a demo.

    Checked across the whole series rather than at today: a stake change part way
    through history is exactly the kind of thing that holds now and not in March.
    """
    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)

    owner_id = db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
    earliest = earliest_snapshot(db_session)
    assert earliest is not None

    for as_of in month_starts(30, TODAY):
        mine = net_worth(db_session, as_of=as_of, viewer_id=owner_id)
        household = net_worth(db_session, as_of=as_of, viewer_id=None)
        assert household.net_worth >= mine.net_worth, (
            f"household is below mine on {as_of}: {household.net_worth} < {mine.net_worth}"
        )


def test_the_partner_is_better_off_than_nothing_once_they_join(db_session: Session) -> None:
    """After the stake change, the household total is strictly larger.

    Equal before it is correct — the partner holds nothing yet. Strictly greater
    afterwards is what says they hold more asset than debt, which is the coherence
    the previous seed lacked.
    """
    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)

    owner_id = db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
    change = db_session.execute(
        text("SELECT min(effective_from) FROM ownership_stakes WHERE owner_user_id != :o"),
        {"o": owner_id},
    ).scalar_one()

    after = change + dt.timedelta(days=60)
    mine = net_worth(db_session, as_of=after, viewer_id=owner_id)
    household = net_worth(db_session, as_of=after, viewer_id=None)

    assert household.net_worth > mine.net_worth


def test_the_part_owned_rental_survives_the_fix(db_session: Session) -> None:
    """Half of it still belongs outside the household — a distinct case worth keeping.

    It is the only account where even the Household view shows less than the asset is
    worth, which is what exercises the difference between "my share" and "all shares".
    """
    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)

    total = db_session.execute(
        text(
            "SELECT sum(s.percentage) FROM ownership_stakes s "
            "JOIN accounts a ON a.id = s.account_id "
            "WHERE a.name = 'Rental property' AND s.effective_to IS NULL"
        )
    ).scalar_one()

    assert total == Decimal("50.00")


def test_the_mortgage_and_the_home_it_is_against_are_shared_together(
    db_session: Session,
) -> None:
    """Sharing a debt without the asset securing it is what broke the picture."""
    seed(db_session, seed_value=DEFAULT_SEED, today=TODAY)

    shared = db_session.execute(
        text(
            "SELECT DISTINCT a.name FROM ownership_stakes s "
            "JOIN accounts a ON a.id = s.account_id "
            "JOIN users u ON u.id = s.owner_user_id "
            "WHERE u.display_name = 'Partner'"
        )
    ).scalars()

    assert {"Mortgage", "Primary residence"} <= set(shared)
