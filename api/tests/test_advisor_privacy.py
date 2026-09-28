"""Nothing the advisor reads leaves through an error report or a log line.

The figures and merchant names below are built at run time, never written whole in this
file: Sentry attaches source lines to stack frames, and a literal here would be found in the
event for the wrong reason.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from pydantic import SecretStr
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.advisor import loop as loop_module
from app.advisor import render
from app.advisor import tools as tools_module
from app.advisor.loop import TurnDeps, run_turn
from app.advisor.model import ScriptedCall, ScriptedModelClient, ToolUse
from app.advisor.store import Store, nested_in
from app.advisor.tools import (
    NoArgs,
    Registry,
    ToolContext,
    ToolResult,
    load_all,
    savepoint_read_only,
)
from app.config import Settings, get_settings
from app.db import get_engine
from app.observability import configure_sentry
from app.schemas.common import ViewScope

FIGURE = render.money(123_456)  # "$1,234.56", never written whole here
MERCHANT = " ".join(["BLUE", "BOTTLE", "COFFEE"])


class Captured(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in (env.get_event() for env in self.envelopes) if e is not None]

    def text(self) -> str:
        return json.dumps(self.events(), default=str)


@pytest.fixture
def sentry() -> Iterator[Captured]:
    captured = Captured()
    configure_sentry("https://public@example.invalid/1", "test", transport=captured)
    yield captured
    sentry_sdk.get_client().close()
    sentry_sdk.init()


def _frame_holding_figures() -> None:
    balance_text = FIGURE  # noqa: F841 — a local variable is what's under test
    merchant_text = MERCHANT  # noqa: F841
    raise ValueError("lookup failed")


def test_a_stack_frame_holding_figures_is_reported_without_them(sentry: Captured) -> None:
    try:
        _frame_holding_figures()
    except ValueError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()

    assert sentry.events(), "an event was captured"
    assert FIGURE not in sentry.text()
    assert MERCHANT not in sentry.text()


def test_the_same_frame_would_leak_with_local_variables_on() -> None:
    """The control: shows the test above would catch the leak it guards against."""
    captured = Captured()
    sentry_sdk.init(
        dsn="https://public@example.invalid/1", transport=captured, include_local_variables=True
    )
    try:
        try:
            _frame_holding_figures()
        except ValueError:
            sentry_sdk.capture_exception()
        sentry_sdk.flush()
        assert FIGURE in captured.text()
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.init()


class Leaky(ToolResult):
    spend_cents: int
    merchant_text: str


def test_a_tool_that_raises_is_reported_by_class_and_ids_only(
    sentry: Captured, db_session: Session
) -> None:
    registry = Registry()

    @registry.tool("spend_leaky", description="A tool that fails holding a result.")
    def spend_leaky(args: NoArgs, session: Session, ctx: ToolContext) -> Leaky:
        result = Leaky(spend_cents=123_456, merchant_text=MERCHANT)
        raise RuntimeError(f"could not finish {result.merchant_text[:0]}")

    ctx = ToolContext(
        today=dt.date(2026, 9, 27),
        user_id=1,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )

    outcome = registry.run("spend_leaky", {}, ctx)
    sentry_sdk.flush()

    assert outcome.status == "error"
    (event,) = sentry.events()
    assert event["message"] == "advisor tool failed: RuntimeError"
    assert event["tags"]["advisor.tool"] == "spend_leaky"
    assert event["tags"]["advisor.call_id"] == outcome.call_id
    assert "exception" not in event
    assert FIGURE not in sentry.text() and "123456" not in sentry.text()
    assert MERCHANT not in sentry.text()


def test_database_errors_reach_an_error_report_without_the_data(sentry: Captured) -> None:
    """Postgres quotes the bad value in its own message; the report withholds messages."""
    assert get_engine().hide_parameters is True

    with get_engine().connect() as connection, pytest.raises(DBAPIError) as caught:
        connection.execute(text("SELECT CAST(:v AS integer)"), {"v": f"{FIGURE} {MERCHANT}"})
    assert "[SQL parameters hidden" in str(caught.value)
    assert FIGURE in str(caught.value), "Postgres quotes it: why the message must go"

    sentry_sdk.capture_exception(caught.value)
    sentry_sdk.flush()

    (event,) = sentry.events()
    assert event["exception"]["values"][-1]["type"] == "DataError"
    assert FIGURE not in sentry.text()
    assert MERCHANT not in sentry.text()


# ── logs ──────────────────────────────────────────────────────────────────────

#: Everything an advisor log line may carry.
ALLOWED_FIELDS = {
    "turn_id",
    "tool",
    "call_id",
    "status",
    "latency_ms",
    "row_count",
    "error",
    "stop_reason",
    "grounding",
    "tool_calls",
}


class Recorder:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, Any]]] = []

    def _record(self, event: str, **fields: Any) -> None:
        self.entries.append((event, fields))

    info = warning = error = debug = _record


def test_advisor_logs_carry_ids_tools_statuses_and_counts_only(
    db_session: Session, owner_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(loop_module, "logger", recorder)
    monkeypatch.setattr(tools_module, "logger", recorder)
    question = "Where did " + "QMARK" + "-4417 go?"
    store = Store(nested_in(db_session))
    now = dt.datetime(2026, 9, 27, 12, tzinfo=dt.UTC)
    conversation = store.create_conversation(owner_id, "mine", "", now)
    client = ScriptedModelClient(
        [
            ScriptedCall(
                tool_calls=[
                    ToolUse("t1", "networth_get", {"view": None}),
                    ToolUse(
                        "t2",
                        "transactions_search",
                        {"start": "2026-09-01", "merchant_query": "ZQ" + "ARG77"},
                    ),
                ]
            ),
            ScriptedCall(text=["Mine: {{c1.net_worth}}."]),
        ]
    )
    deps = TurnDeps(
        client=client,
        store=store,
        registry=load_all(),
        tool_sessions=savepoint_read_only(db_session),
        settings=Settings(
            database_url="postgresql://unused",
            advisor_enabled=True,
            anthropic_api_key=SecretStr("test-key-not-real"),
        ),
        now=lambda: now,
    )

    async def run() -> None:
        async for _ in run_turn(
            deps,
            conversation_id=conversation,
            user_id=owner_id,
            view=ViewScope.MINE,
            question=question,
        ):
            pass

    asyncio.run(run())

    events = [event for event, _ in recorder.entries]
    assert events.count("advisor_tool_call") == 2
    assert "advisor_turn_finished" in events
    for event, fields in recorder.entries:
        assert set(fields) <= ALLOWED_FIELDS, (event, set(fields) - ALLOWED_FIELDS)
    logged = json.dumps(recorder.entries, default=str)
    assert "QMARK" not in logged  # the question
    assert "ZQARG77" not in logged  # an argument
    assert "$0.00" not in logged and "net_worth" not in logged  # a result


# ── the demo ──────────────────────────────────────────────────────────────────


def test_the_demo_can_never_be_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ADVISOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    try:
        assert get_settings().advisor_active is False
    finally:
        get_settings.cache_clear()
