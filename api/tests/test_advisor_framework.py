"""The tool registry: strict schemas, validation, budgets, read-only execution, audit.

Throwaway tools registered on a local registry exercise it. The real tools arrive in
084-093 and are linted by `test_every_registered_tool_passes_the_lint`.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.advisor.tools import (
    CallIds,
    Id,
    MemoryAudit,
    PeriodArg,
    Registry,
    ToolArgs,
    ToolContext,
    ToolInputError,
    ToolResult,
    TurnBudget,
    fresh_read_only_session,
    lint_args_model,
    lint_tool,
    load_all,
    savepoint_read_only,
    strict_schema,
)
from app.models.account import Institution
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope

TODAY = dt.date(2026, 9, 27)


class CountArgs(ToolArgs):
    view: ViewScope | None = Field(default=None, description="Mine or household.")
    limit: int = Field(default=10, ge=1, le=25, description="How many.")


class CountResult(ToolResult):
    institutions: int
    total_cents: int


class RowsResult(ToolResult):
    names_text: list[str]

    def row_count(self) -> int:
        return len(self.names_text)


class WriteArgs(ToolArgs):
    pass


@pytest.fixture
def registry() -> Registry:
    reg = Registry()

    @reg.tool(
        "data_count",
        description="Counts institutions. Use it to test the framework.",
        label=lambda args: f"Count, up to {args.limit}",
    )
    def data_count(args: CountArgs, session: Session, ctx: ToolContext) -> CountResult:
        count = session.execute(select(func.count()).select_from(Institution)).scalar_one()
        return CountResult(as_of=ctx.today, view=args.view, institutions=count, total_cents=12_345)

    @reg.tool("data_rows", description="Returns rows. It exists to spend the budget.", shape="rows")
    def data_rows(args: CountArgs, session: Session, ctx: ToolContext) -> RowsResult:
        return RowsResult(names_text=[f"row {i}" for i in range(args.limit)])

    @reg.tool("data_write", description="Tries to write. It must not be able to.")
    def data_write(args: WriteArgs, session: Session, ctx: ToolContext) -> CountResult:
        session.execute(text("INSERT INTO institutions (name) VALUES ('should not exist')"))
        return CountResult(institutions=0, total_cents=0)

    @reg.tool("data_future", description="Refuses a date. It checks ToolInputError.")
    def data_future(args: WriteArgs, session: Session, ctx: ToolContext) -> CountResult:
        raise ToolInputError("That date is after today.")

    return reg


@pytest.fixture
def ctx(db_session: Session, owner_id: int) -> ToolContext:
    return ToolContext(
        today=TODAY,
        user_id=owner_id,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )


# ── schemas ───────────────────────────────────────────────────────────────────


def test_definitions_are_sorted_and_strict(registry: Registry) -> None:
    definitions = registry.definitions()

    assert [d.name for d in definitions] == sorted(d.name for d in definitions)
    schema = next(d for d in definitions if d.name == "data_count").input_schema
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["view", "limit"]
    limit = schema["properties"]["limit"]
    # Strict schemas reject numeric bounds: they move into the description, and Pydantic
    # still enforces them.
    assert "minimum" not in limit and "maximum" not in limit
    assert "at least 1" in limit["description"] and "at most 25" in limit["description"]
    # The enum is inlined rather than referenced.
    assert "$ref" not in json.dumps(schema)
    assert "household" in json.dumps(schema["properties"]["view"])


def test_a_period_argument_is_strict_all_the_way_down() -> None:
    class Args(ToolArgs):
        period: PeriodArg

    schema = strict_schema(Args)
    period = schema["properties"]["period"]
    assert period["additionalProperties"] is False
    assert period["required"] == ["preset", "start", "end"]


# ── the lint ──────────────────────────────────────────────────────────────────


def test_the_lint_accepts_safe_arguments() -> None:
    class Safe(ToolArgs):
        view: ViewScope
        period: PeriodArg
        limit: int = Field(ge=1, le=25)
        merchant_query: str | None = Field(
            default=None, pattern=r"^[A-Za-z0-9 &'.*#-]{2,40}$", max_length=40
        )
        ids: list[Id] = Field(default_factory=list, max_length=10)

    assert lint_args_model(Safe, "safe") == []


@pytest.mark.parametrize(
    ("field_type", "field_default", "problem"),
    [
        (str, Field(default="x"), "free text is only allowed"),
        (int, Field(default=1, ge=0), "bounded both ways"),
        (list[str], Field(default_factory=list), "maxItems"),
    ],
)
def test_the_lint_refuses_unsafe_arguments(
    field_type: Any, field_default: Any, problem: str
) -> None:
    unsafe = type(
        "Unsafe", (ToolArgs,), {"__annotations__": {"note": field_type}, "note": field_default}
    )
    problems = lint_args_model(unsafe, "unsafe")
    assert any(problem in p for p in problems), problems


def test_the_lint_refuses_a_search_pattern_that_admits_a_url() -> None:
    class Leaky(ToolArgs):
        merchant_query: str = Field(pattern=r"^.{2,40}$", max_length=40)

    assert any("admits a URL" in p for p in lint_args_model(Leaky, "leaky"))


def test_tool_names_and_descriptions_follow_the_convention(registry: Registry) -> None:
    assert lint_tool(registry.spec("data_count")) == []

    reg = Registry()

    @reg.tool("fetchstuff", description="Too short")
    def bad(args: WriteArgs, session: Session, ctx: ToolContext) -> CountResult:
        return CountResult(institutions=0, total_cents=0)

    problems = lint_tool(reg.spec("fetchstuff"))
    assert any("names are" in p for p in problems)
    assert any("two sentences" in p for p in problems)


def test_every_registered_tool_passes_the_lint() -> None:
    """The real catalog. Each ticket that adds tools adds its module to TOOL_MODULES."""
    registry = load_all()
    problems = [p for name in registry.names() for p in lint_tool(registry.spec(name))]
    assert problems == []


# ── running ───────────────────────────────────────────────────────────────────


def test_a_call_renders_audits_and_labels(registry: Registry, ctx: ToolContext) -> None:
    outcome = registry.run("data_count", {"view": "household", "limit": 5}, ctx)

    assert outcome.status is LookupStatus.OK
    assert outcome.call_id == "c1"
    assert outcome.label == "Count, up to 5"
    assert outcome.arguments == "view=household, limit=5"
    assert outcome.as_of == TODAY and outcome.view is ViewScope.HOUSEHOLD
    assert "$123.45 [c1.total]" in outcome.content
    assert "c1.total" in outcome.figures
    assert isinstance(ctx.audit, MemoryAudit)
    assert ctx.audit.outcomes == [outcome]


def test_invalid_arguments_are_a_result_not_an_exception(
    registry: Registry, ctx: ToolContext
) -> None:
    outcome = registry.run("data_count", {"limit": 99}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "limit" in outcome.content and "call again" in outcome.content


def test_extra_arguments_are_refused(registry: Registry, ctx: ToolContext) -> None:
    outcome = registry.run("data_count", {"limit": 1, "url": "https://evil.example"}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS


def test_an_unknown_tool_names_the_real_ones(registry: Registry, ctx: ToolContext) -> None:
    outcome = registry.run("web_fetch", {}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "data_count" in outcome.content


def test_a_tool_input_error_is_returned_to_the_model(registry: Registry, ctx: ToolContext) -> None:
    outcome = registry.run("data_future", {}, ctx)

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "after today" in outcome.content


def test_call_ids_continue_across_a_conversation(registry: Registry, ctx: ToolContext) -> None:
    ctx.call_ids = CallIds(issued=4)

    assert registry.run("data_count", {}, ctx).call_id == "c5"


# ── budgets ───────────────────────────────────────────────────────────────────


def test_the_call_budget_is_enforced(registry: Registry, ctx: ToolContext) -> None:
    ctx.budget = TurnBudget(max_calls=2)

    statuses = [registry.run("data_count", {}, ctx).status for _ in range(3)]

    assert statuses == [LookupStatus.OK, LookupStatus.OK, LookupStatus.BUDGET_EXHAUSTED]


def test_the_row_budget_is_enforced(registry: Registry, ctx: ToolContext) -> None:
    ctx.budget = TurnBudget(max_rows=30)

    first = registry.run("data_rows", {"limit": 25}, ctx)
    second = registry.run("data_rows", {"limit": 10}, ctx)

    assert (first.status, first.row_count) == (LookupStatus.OK, 25)
    assert second.status is LookupStatus.BUDGET_EXHAUSTED
    assert ctx.budget.rows == 25


# ── read-only ─────────────────────────────────────────────────────────────────


def test_a_write_fails_inside_the_test_savepoint(
    registry: Registry, ctx: ToolContext, db_session: Session
) -> None:
    before = db_session.execute(select(func.count()).select_from(Institution)).scalar_one()

    outcome = registry.run("data_write", {}, ctx)

    assert outcome.status is LookupStatus.ERROR
    assert outcome.error == "ReadOnlySqlTransaction"
    # The outer transaction is untouched and still writable afterwards.
    after = db_session.execute(select(func.count()).select_from(Institution)).scalar_one()
    assert after == before
    db_session.execute(text("INSERT INTO institutions (name) VALUES ('writable again')"))


def test_a_write_fails_in_a_fresh_production_session(registry: Registry, owner_id: int) -> None:
    """The path production takes: a new session, not the test fixture's. ADR 0005's
    lesson — a fixture that removes a behaviour hides bugs in it, so test it directly."""
    ctx = ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=fresh_read_only_session
    )

    outcome = registry.run("data_write", {}, ctx)

    assert outcome.status is LookupStatus.ERROR
    assert outcome.error == "ReadOnlySqlTransaction"


def test_a_statement_timeout_is_set(db_session: Session) -> None:
    @contextmanager
    def probe() -> Iterator[str]:
        with savepoint_read_only(db_session, timeout_ms=1234)() as session:
            yield str(session.execute(text("SHOW statement_timeout")).scalar_one())

    with probe() as timeout:
        assert timeout == "1234ms"
