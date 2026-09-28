"""The projection tools: the band and its gaps, the bounds, what-if differences equal to the
engine run twice, and a limitation — never a projection — when data is missing."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.advisor.tools.projections import WhatIfResult
from app.models.account import Account
from app.models.enums import AssetClass
from app.models.planning import MemberProfile
from app.schemas.common import ViewScope
from app.services import allocations
from app.services.analysis import projections as engine
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake
from evals import synthetic_returns

JAN = dt.date(2026, 1, 1)
TODAY = dt.date(2026, 8, 18)


@pytest.fixture
def ctx(db_session: Session, owner_id: int) -> ToolContext:
    return ToolContext(
        today=TODAY,
        user_id=owner_id,
        view=ViewScope.HOUSEHOLD,
        sessions=savepoint_read_only(db_session),
    )


@pytest.fixture
def own(db_session: Session, make_account: Callable[..., int], owner_id: int) -> Callable[..., int]:
    def _own(
        name: str, subtype: str, balance: str, kind: str = "illiquid_asset", **pcts: str
    ) -> int:
        account = make_account(name=name, kind=kind, subtype=subtype)
        create_initial_stake(db_session, account, owner_id, JAN)
        record_balance(db_session, account, TODAY, Decimal(balance))
        if pcts:
            allocations.set_allocation(
                db_session,
                db_session.get_one(Account, account),
                {AssetClass(cls): Decimal(pct) for cls, pct in pcts.items()},
                JAN,
            )
        return account

    return _own


def _treat(db_session: Session, *accounts: int) -> None:
    """Record each account's tax treatment, as the API does on create."""
    for account_id in accounts:
        account = db_session.get_one(Account, account_id)
        account.tax_treatment = allocations.default_tax_treatment(account.subtype)
    db_session.flush()


@pytest.fixture
def household(
    db_session: Session,
    own: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
    owner_id: int,
) -> dict[str, int]:
    """Born 1984, aiming for 2039; a brokerage and a 401k; $6,000 in and $4,000 out a month."""
    db_session.add(MemberProfile(user_id=owner_id, birth_year=1984, target_retirement_year=2039))
    ids = {
        "brokerage": own(
            "Brokerage", "brokerage", "300000.00", kind="liquid_asset", us_equity="100"
        ),
        "401k": own("401k", "401k", "400000.00", us_equity="60", bonds="40"),
        "checking": own("Checking", "checking", "10000.00", kind="liquid_asset"),
    }
    _treat(db_session, *ids.values())
    days = [dt.date(2025, m, 5) for m in range(8, 13)] + [dt.date(2026, m, 5) for m in range(1, 8)]
    for day in days:
        make_transaction(ids["checking"], day, "6000.00", category_id=category_ids["Salary"])
        make_transaction(ids["checking"], day, "-4000.00", category_id=category_ids["Groceries"])
    db_session.flush()
    return ids


def _run(name: str, args: dict[str, Any], ctx: ToolContext) -> Any:
    return load_all().run(name, {"view": None, **args}, ctx)


# ── projection_retirement ─────────────────────────────────────────────────────


@pytest.mark.usefixtures("household")
def test_the_retirement_tool_returns_a_band_with_its_assumptions(ctx: ToolContext) -> None:
    with synthetic_returns():
        outcome = _run("projection_retirement", {}, ctx)

    assert outcome.status == "ok"
    data = json.loads(outcome.content)["data"]
    band = data["band"]
    assert [row["rate_pct"].split(" ")[0] for row in band["by_rate"]] == [
        "3.00%",
        "3.50%",
        "4.00%",
        "4.50%",
    ]
    assert band["rates_at_year"] == 2039
    assert data["assumptions_id"] is not None
    assert data["contribution_source"] == "trailing_12_months"
    assert any("59½" in line for line in data["limitations"])


def test_retirement_arguments_are_bounded(ctx: ToolContext) -> None:
    for args in (
        {"retire_year": 2026},  # this year: already past
        {"retire_year": 2087},  # more than sixty years out
        {"annual_spend_cents": 100_000_001},
        {"annual_spend_cents": -1},
    ):
        assert _run("projection_retirement", args, ctx).status == "invalid_args", args


def test_no_returns_table_is_a_limitation_not_a_projection(
    household: dict[str, int], ctx: ToolContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(engine, "RETURNS_PATH", tmp_path / "missing.csv")

    outcome = _run("projection_retirement", {}, ctx)

    data = json.loads(outcome.content)["data"]
    assert (data["unavailable"], data["limitation_kind"]) == ("no_returns_table", "projections")
    assert "band" not in data


def test_no_tax_treatment_recorded_is_a_limitation_not_a_projection(
    db_session: Session, own: Callable[..., int], owner_id: int, ctx: ToolContext
) -> None:
    db_session.add(MemberProfile(user_id=owner_id, birth_year=1984))
    own("Brokerage", "brokerage", "300000.00", kind="liquid_asset", us_equity="100")  # untreated

    with synthetic_returns():
        outcome = _run("projection_retirement", {"annual_spend_cents": 4_000_000}, ctx)

    data = json.loads(outcome.content)["data"]
    assert (data["unavailable"], data["limitation_kind"]) == ("no_tax_treatment", "tax_treatment")
    assert "band" not in data and data["buckets"] == []  # nulls are not rendered


def test_an_assumed_tax_treatment_is_named_as_a_gap(
    db_session: Session,
    household: dict[str, int],
    own: Callable[..., int],
    ctx: ToolContext,
) -> None:
    own("Old IRA", "ira", "20000.00", bonds="100")  # its treatment was never recorded

    with synthetic_returns():
        outcome = _run("projection_retirement", {}, ctx)

    data = json.loads(outcome.content)["data"]
    assert [gap["name_text"] for gap in data["tax_treatment_assumed"]] == ["Old IRA"]


def test_no_birth_year_is_a_limitation(ctx: ToolContext) -> None:
    with synthetic_returns():
        outcome = _run("projection_retirement", {}, ctx)

    data = json.loads(outcome.content)["data"]
    assert data["unavailable"] == "no_birth_year"


# ── projection_what_if ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("extra_monthly_saving", 1_000_001),
        ("spend_change_bps", 5001),
        ("spend_change_bps", -5001),
        ("retire_year_shift", 16),
        ("retire_year_shift", -16),
    ],
)
def test_what_if_changes_are_bounded(ctx: ToolContext, change: str, value: int) -> None:
    assert _run("projection_what_if", {"change": change, "value": value}, ctx).status == (
        "invalid_args"
    )


@pytest.mark.usefixtures("household")
@pytest.mark.parametrize(
    ("change", "value", "edit"),
    [
        (
            "extra_monthly_saving",
            50_000,
            lambda plan, base: replace(
                plan,
                annual_contribution=plan.annual_contribution + Decimal("6000"),
                contribution_source="override",
            ),
        ),
        (
            "spend_change_bps",
            -1000,
            lambda plan, base: replace(plan, annual_spending=plan.annual_spending * Decimal("0.9")),
        ),
        (
            "retire_year_shift",
            3,
            lambda plan, base: replace(plan, target_retirement_year=base.rates_at_year + 3),
        ),
    ],
)
def test_what_if_differences_equal_the_engine_run_twice(
    db_session: Session,
    ctx: ToolContext,
    owner_id: int,
    change: str,
    value: int,
    edit: Callable[[engine.Plan, engine.Projection], engine.Plan],
) -> None:
    with synthetic_returns():
        spec = load_all().spec("projection_what_if")
        result = cast(
            WhatIfResult,
            spec.fn(
                spec.args_model.model_validate({"change": change, "value": value}), db_session, ctx
            ),
        )
        table = engine.returns_table()
        plan = engine.plan_for(db_session, TODAY, owner_id, None)
        base = engine.project(plan, table)
        scenario = engine.project(edit(plan, base), table)

    assert result.base is not None and result.scenario is not None
    assert result.differences is not None
    assert result.base.earliest_year == base.earliest_year
    assert result.scenario.earliest_year == scenario.earliest_year
    expected_change = (
        None
        if base.earliest_year is None or scenario.earliest_year is None
        else scenario.earliest_year - base.earliest_year
    )
    assert result.differences.earliest_year_change == expected_change
    assert [d.bootstrap_success_bps for d in result.differences.success_change_bps] == [
        s.bootstrap_success_bps - b.bootstrap_success_bps
        for s, b in zip(scenario.by_rate, base.by_rate, strict=True)
    ]
    assert result.assumptions_id == plan.assumptions_id


def test_what_if_without_data_is_a_limitation(ctx: ToolContext) -> None:
    with synthetic_returns():
        outcome = _run("projection_what_if", {"change": "retire_year_shift", "value": 2}, ctx)

    data = json.loads(outcome.content)["data"]
    assert data["unavailable"] == "no_birth_year"
    assert "base" not in data and "differences" not in data
