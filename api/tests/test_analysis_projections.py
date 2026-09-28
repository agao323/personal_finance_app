"""Projections: one path by hand, the bucket order, the 59½ rule, the band, reproducibility,
the returns table's header, and the plan built from the database with unknowns left out."""

from __future__ import annotations

import datetime as dt
import textwrap
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AssetClass
from app.models.planning import MemberProfile
from app.services import allocations
from app.services.analysis import projections
from app.services.analysis.projections import Plan, ProjectionUnavailableError
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake

SYNTHETIC = Path(__file__).parent / "fixtures" / "returns_synthetic.csv"
JAN = dt.date(2026, 1, 1)
TODAY = dt.date(2026, 8, 18)
ALL_US = {AssetClass.US_EQUITY: Decimal(1)}


def _plan(**overrides: object) -> Plan:
    fields: dict[str, object] = {
        "start_year": 2027,
        "birth_year": 1986,
        "balances": {"taxable": Decimal("100000")},
        "weights": {"taxable": ALL_US},
        "annual_contribution": Decimal("10000"),
        "annual_spending": Decimal("40000"),
        "healthcare_pre65": Decimal("0"),
        "tax_deferred_rate": Decimal("0.15"),
        "withdrawal_rates_bps": [300, 350, 400, 450],
    }
    fields.update(overrides)
    return Plan(**fields)  # type: ignore[arg-type]


def _flat(rate: str, years: int) -> list[dict[AssetClass, Decimal]]:
    return [{cls: Decimal(rate) for cls in AssetClass} for _ in range(years)]


# ── one path, by hand ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("birth_year", "success", "failed"), [(1936, True, None), (1937, False, 2032)]
)
def test_a_single_sequence_checked_by_hand(
    birth_year: int, success: bool, failed: int | None
) -> None:
    # $100,000, $10,000 saved a year, 5% real every year, retire in 2029 on $40,000 a year:
    #   2027 (100,000 + 10,000) x 1.05 = 115,500
    #   2028 (115,500 + 10,000) x 1.05 = 131,775
    #   2029 131,775 - 40,000 = 91,775      → 96,363.75
    #   2030 96,363.75 - 40,000 = 56,363.75 → 59,181.9375
    #   2031 59,181.9375 - 40,000 = 19,181.9375 → 20,141.034375
    #   2032 20,141.03 cannot meet 40,000.
    # Born 1936, the horizon ends at 95 in 2031: it lasts. Born 1937, it runs to 2032: it fails.
    plan = _plan(birth_year=birth_year)
    path = projections.prepare(plan, _flat("0.05", plan.horizon))

    outcome = projections.run_path(plan, path.factors, path.starts, 2, lambda age: Decimal("40000"))

    assert [start[0] for start in path.starts[:3]] == [
        Decimal("100000"),
        Decimal("115500.00"),
        Decimal("131775.0000"),
    ]
    assert [row[0] for row in outcome.trail[:3]] == [
        Decimal("91775.0000"),
        Decimal("56363.750000"),
        Decimal("19181.93750000"),
    ]
    assert (outcome.success, outcome.failed_year) == (success, failed)


# ── the bucket order and the 59½ rule ─────────────────────────────────────────


def test_withdrawals_go_taxable_then_tax_deferred_grossed_up_then_roth() -> None:
    balances = [Decimal("1000"), Decimal("10000"), Decimal("5000"), Decimal("5000")]

    short = projections.withdraw(balances, Decimal("3000"), 61, Decimal("0.20"))

    # 1,000 taxable, then 2,000 net from tax-deferred: 2,500 gross at 20%. Roth untouched.
    assert short == 0
    assert balances == [Decimal("0"), Decimal("7500"), Decimal("5000"), Decimal("5000")]


def test_tax_deferred_money_is_not_drawn_before_59_and_a_half() -> None:
    balances = [Decimal("1000"), Decimal("10000"), Decimal("5000"), Decimal("5000")]

    short = projections.withdraw(balances, Decimal("8000"), 59, Decimal("0.20"))

    # Taxable then Roth; tax-deferred locked at 59, the HSA locked before 65.
    assert short == Decimal("2000")
    assert balances == [Decimal("0"), Decimal("10000"), Decimal("0"), Decimal("5000")]


def test_the_hsa_is_roth_like_from_65() -> None:
    balances = [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("5000")]

    assert projections.withdraw(balances, Decimal("1000"), 65, Decimal("0.2")) == 0
    assert balances[3] == Decimal("4000")


@pytest.mark.parametrize(("retire_at", "success"), [(55, False), (60, True)])
def test_a_retirement_funded_only_by_a_401k_waits_for_59_and_a_half(
    retire_at: int, success: bool
) -> None:
    plan = _plan(
        balances={"tax_deferred": Decimal("2000000")},
        weights={"tax_deferred": ALL_US},
        annual_contribution=Decimal("0"),
    )
    path = projections.prepare(plan, _flat("0.00", plan.horizon))
    index = plan.birth_year + retire_at - plan.start_year

    outcome = projections.run_path(
        plan, path.factors, path.starts, index, lambda age: Decimal("40000")
    )

    assert outcome.success is success
    if not success:
        assert outcome.failed_year == plan.birth_year + retire_at


# ── the band ──────────────────────────────────────────────────────────────────


def _table() -> projections.ReturnsTable:
    return projections.load_returns(SYNTHETIC)


def test_a_projection_is_a_band_never_a_single_number() -> None:
    result = projections.project(_plan(), _table(), bootstrap_count=50)

    assert [r.rate_bps for r in result.by_rate] == [300, 350, 400, 450]
    with pytest.raises(ValueError, match="never a single number"):
        projections.Projection(
            plan=result.plan,
            returns_source=result.returns_source,
            rates_at_year=result.rates_at_year,
            by_rate=result.by_rate[:1],
            by_year=result.by_year,
            earliest_year=result.earliest_year,
            historical_paths=result.historical_paths,
            bootstrap_paths=result.bootstrap_paths,
            seed=result.seed,
            limitations=result.limitations,
        )
    with pytest.raises(ValueError, match="band"):
        projections.project(_plan(withdrawal_rates_bps=[400]), _table(), bootstrap_count=50)


def test_success_falls_as_the_withdrawal_rate_rises_and_carries_the_assumptions() -> None:
    plan = _plan(
        balances={"taxable": Decimal("1500000")},
        target_retirement_year=2030,
        assumptions_id=7,
    )

    result = projections.project(plan, _table(), bootstrap_count=200)

    boot = [r.bootstrap_success_bps for r in result.by_rate]
    assert boot == sorted(boot, reverse=True)
    assert result.assumptions_id == 7
    assert result.rates_at_year == 2030
    assert result.historical_paths == 40  # every start year in the table
    assert result.returns_source.startswith("SYNTHETIC")
    assert any("59½" in line for line in result.limitations)


def test_the_earliest_year_reaching_90_percent_is_the_first_that_does() -> None:
    result = projections.project(
        _plan(annual_contribution=Decimal("30000")), _table(), bootstrap_count=200
    )

    assert result.earliest_year is not None
    reached = {
        y.year: min(y.historical_success_bps, y.bootstrap_success_bps) for y in result.by_year
    }
    assert reached[result.earliest_year] >= 9000
    if result.earliest_year - 1 in reached:
        assert reached[result.earliest_year - 1] < 9000


def test_the_bootstrap_is_reproducible_run_to_run() -> None:
    table = _table()

    first = projections.project(_plan(), table, bootstrap_count=100, seed=11)
    again = projections.project(_plan(), table, bootstrap_count=100, seed=11)

    assert first.by_rate == again.by_rate and first.by_year == again.by_year
    assert projections.bootstrap_paths(table, 30, 5, seed=11) == projections.bootstrap_paths(
        table, 30, 5, seed=11
    )
    assert projections.bootstrap_paths(table, 30, 5, seed=11) != projections.bootstrap_paths(
        table, 30, 5, seed=12
    )


def test_historical_windows_start_in_every_year_and_wrap() -> None:
    table = _table()

    paths = projections.historical_paths(table, 45)

    assert len(paths) == len(table.rows) == 40
    assert paths[39][0] is table.rows[39] and paths[39][1] is table.rows[0]


# ── the returns table ─────────────────────────────────────────────────────────


def test_the_returns_table_must_name_its_source_and_licence(tmp_path: Path) -> None:
    unlabelled = tmp_path / "returns.csv"
    unlabelled.write_text(
        textwrap.dedent(
            """\
            # source: somewhere
            year,us_equity,intl_equity,bonds,cash,real_estate,other
            2000,0.1,0.1,0.02,0.01,0.03,0.0
            """
        )
    )

    with pytest.raises(ValueError, match="source and licence"):
        projections.load_returns(unlabelled)
    assert _table().synthetic is True


def test_there_is_no_projection_without_a_real_returns_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(projections, "RETURNS_PATH", tmp_path / "missing.csv")
    with pytest.raises(ProjectionUnavailableError) as missing:
        projections.default_returns()
    assert missing.value.reason == "no_returns_table"

    monkeypatch.setattr(projections, "RETURNS_PATH", SYNTHETIC)
    with pytest.raises(ProjectionUnavailableError, match="synthetic"):
        projections.default_returns()


# ── the plan, from the database ───────────────────────────────────────────────


@pytest.fixture
def household(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
    owner_id: int,
) -> dict[str, int]:
    """A brokerage and a 401k with allocations, an IRA with none, a 529, and a year of pay and
    spending: $6,000 in and $4,000 out every month."""
    db_session.add(MemberProfile(user_id=owner_id, birth_year=1986))

    def own(name: str, subtype: str, balance: str, kind: str = "illiquid_asset") -> int:
        account = make_account(name=name, kind=kind, subtype=subtype)
        create_initial_stake(db_session, account, owner_id, JAN)
        record_balance(db_session, account, TODAY, Decimal(balance))
        return account

    ids = {
        "brokerage": own("Brokerage", "brokerage", "50000.00", kind="liquid_asset"),
        "401k": own("401k", "401k", "200000.00"),
        "ira": own("Old IRA", "ira", "30000.00"),
        "529": own("College", "529", "15000.00"),
        "checking": own("Checking", "checking", "8000.00", kind="liquid_asset"),
    }
    for name, shares in (
        ("brokerage", {"us_equity": "100"}),
        ("401k", {"us_equity": "60", "bonds": "40"}),
    ):
        allocations.set_allocation(
            db_session,
            db_session.get_one(Account, ids[name]),
            {AssetClass(cls): Decimal(pct) for cls, pct in shares.items()},
            JAN,
        )
    days = [dt.date(2025, m, 5) for m in range(8, 13)] + [dt.date(2026, m, 5) for m in range(1, 8)]
    for day in days:
        make_transaction(ids["checking"], day, "6000.00", category_id=category_ids["Salary"])
        make_transaction(ids["checking"], day, "-4000.00", category_id=category_ids["Groceries"])
    db_session.flush()
    return ids


def test_the_plan_keeps_buckets_apart_and_leaves_unknowns_out(
    db_session: Session, household: dict[str, int], owner_id: int
) -> None:
    plan = projections.plan_for(db_session, TODAY, owner_id, None)

    assert plan.balances == {
        "taxable": Decimal("58000.00"),  # the brokerage and checking (cash)
        "tax_deferred": Decimal("200000.00"),  # the 401k; the IRA has no allocation
        "roth": Decimal("0"),
        "hsa": Decimal("0"),
    }
    assert plan.weights["tax_deferred"] == {
        AssetClass.US_EQUITY: Decimal("0.6"),
        AssetClass.BONDS: Decimal("0.4"),
    }
    assert plan.excluded_unknown == Decimal("30000.00")
    assert plan.excluded_education == Decimal("15000.00")
    assert (plan.annual_spending, plan.annual_contribution) == (
        Decimal("48000.00"),
        Decimal("24000.00"),
    )
    assert plan.withdrawal_rates_bps == [300, 350, 400, 450]
    assert plan.assumptions_id is not None

    result = projections.project(plan, _table(), bootstrap_count=50)

    assert result.assumptions_id == plan.assumptions_id
    assert "$30,000.00 in accounts with no allocation entered is left out." in result.limitations


def test_no_birth_year_means_no_projection(db_session: Session, owner_id: int) -> None:
    with pytest.raises(ProjectionUnavailableError) as raised:
        projections.plan_for(db_session, TODAY, owner_id, None)

    assert raised.value.reason == "no_birth_year"
