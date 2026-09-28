"""Grounding, policy checks, answer post-processing, limitations — and the regeneration path.

The table below is the specification in examples: each answer string with the verdict every
figure in it should get. The `hypothesis` properties pin the two claims the design rests on:
every form `render.py` produces is accepted, and a value one unit off is not.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from app.advisor import answer, grounding, policy, render
from app.advisor.grounding import Evidence, StreamResolver, check
from app.advisor.loop import TurnDeps, run_turn
from app.advisor.model import ModelRequest, ScriptedCall, ScriptedModelClient, ToolUse
from app.advisor.render import Figure
from app.advisor.store import Store, nested_in
from app.advisor.tools import ToolResult, load_all, savepoint_read_only
from app.config import Settings
from app.models.advisor import AdvisorTurn
from app.schemas.advisor import FigureStatus, PolicyCheck
from app.schemas.common import ViewScope

NOW = dt.datetime(2026, 9, 27, 15, 0, tzinfo=dt.UTC)


class Item(BaseModel):
    name_text: str


class Balances(ToolResult):
    net_worth_cents: int
    change_bps: int
    runway_months_tenths: int
    subscription_count: int
    stale_account_count: int
    big_cents: int
    items: list[Item]


class Spend(ToolResult):
    total_cents: int


def _evidence() -> Evidence:
    evidence = Evidence()
    scoped = Balances(
        as_of=dt.date(2026, 9, 27),
        view=ViewScope.MINE,
        net_worth_cents=123_456,
        change_bps=1_234,
        runway_months_tenths=234,
        subscription_count=3,
        stale_account_count=2,
        big_cents=1_234_567_890,
        items=[Item(name_text=f"Account {n}") for n in "ABCDE"],
    )
    spend = Spend(as_of=dt.date(2026, 9, 27), total_cents=-98_765)
    evidence.add(render.render("networth_get", "c2", scoped).text)
    evidence.add(render.render("spend_by_category", "c3", spend).text)
    return evidence


EVIDENCE = _evidence()

V, M, U = "verified", "matched", "unverified"

TABLE: list[tuple[str, list[str]]] = [
    # references
    ("Your net worth is {{c2.net_worth}}.", [V]),
    ("Your net worth is {{ c2.net_worth }}.", [V]),
    ("It changed {{c2.change_pct}}.", [V]),
    ("Runway is {{c2.runway_months}}.", [V]),
    ("Spend was {{c3.total}}.", [V]),
    ("{{c9.net_worth}}", [U]),
    ("{{c2.nope}}", [U]),
    ("{{c2.net_worth}} and {{c2.nope}}", [V, U]),
    ("{{c2.net_worth}} and $1,235", [V, M]),
    ("{{c2.net_worth", []),
    # money, exact
    ("$1,234.56", [M]),
    ("$1234.56", [M]),
    ("-$1,234.56", [M]),
    ("$-1,234.56", [M]),
    ("$1,234.57", [U]),
    ("$1,234.55", [U]),
    ("$987.65", [M]),
    ("$1,234.56 [c2.net_worth]", [M]),
    # money, whole dollars half-up
    ("$1,235", [M]),
    ("$1,234", [U]),
    ("$988", [M]),
    ("-$988", [M]),
    ("$12,345,679", [M]),
    ("$12,345,678", [U]),
    # money, one-decimal k and M
    ("$1.2k", [M]),
    ("$1.2K", [M]),
    ("$1.3k", [U]),
    ("$1.0k", [M]),
    ("$12.3M", [M]),
    ("$12.35M", [U]),
    # money, not canonical
    ("$1k", [U]),
    ("$1,234.5", [U]),
    ("about $1,200", [U]),
    ("$0.00", [U]),
    # percentages
    ("12.34%", [M]),
    ("12.3%", [M]),
    ("12%", [M]),
    ("12.35%", [U]),
    ("13%", [U]),
    ("-12.34%", [M]),
    # months
    ("23.4 months", [M]),
    ("23 months", [M]),
    ("24 months", [U]),
    ("23.5 months", [U]),
    # unit counts
    ("3 subscriptions", [M]),
    ("2 stale accounts", [M]),
    ("5 accounts", [M]),
    ("4 subscriptions", [U]),
    ("12,000 transactions", [U]),
    ("3 of the 5 accounts", [M, M]),
    # not figures
    ("on Sep 27", []),
    ("since June 30 last year", []),
    ("in 2026", []),
    ("as of 2026-09-27", []),
    ("1. Check the balance first.", []),
    ("the 2nd largest", []),
    ("over the last 3 months", []),
    ("in the next 30 days", []),
    ("Q3 spending", []),
    ("Open [[screen:cards]] to mark it used.", []),
    ("Nothing to check here.", []),
    # several at once
    ("$1,234.56 and 12.34% over 23.4 months", [M, M, M]),
    ("{{c2.net_worth}} (Mine), about $1,200 more than last year", [V, U]),
]


@pytest.mark.parametrize(("text", "verdicts"), TABLE)
def test_the_verdict_table(text: str, verdicts: list[str]) -> None:
    checked = check(text, EVIDENCE)

    assert [f.status.value for f in checked.figures] == verdicts


def test_the_table_is_at_least_fifty_answers() -> None:
    assert len(TABLE) >= 50


def test_a_reference_is_written_in_and_its_span_points_at_it() -> None:
    checked = check("Net worth {{c2.net_worth}}, runway {{c2.runway_months}}.", EVIDENCE)

    assert checked.text == "Net worth $1,234.56, runway 23.4 months."
    first, second = checked.figures
    assert checked.text[first.start : first.end] == "$1,234.56"
    assert (first.source and first.source.call_id, first.source and first.source.path) == (
        "c2",
        "net_worth",
    )
    assert checked.text[second.start : second.end] == "23.4 months"


def test_an_unresolved_reference_stays_visible() -> None:
    checked = check("You have {{c9.cash}}.", EVIDENCE)

    assert checked.text == "You have {{c9.cash}}."
    assert checked.unverified == ["{{c9.cash}}"]


def test_a_matched_figure_names_where_it_matched() -> None:
    (figure,) = check("$1,235", EVIDENCE).figures

    assert figure.source is not None
    assert (figure.source.call_id, figure.source.path) == ("c2", "net_worth")


def test_figures_from_the_question_are_ignored() -> None:
    checked = check(
        "Spending $5,000 on a trip would leave you short.", EVIDENCE, question="$5,000?"
    )

    assert checked.figures == []


def test_evidence_ignores_errors_and_reads_scopes() -> None:
    evidence = Evidence()
    evidence.add("The lookup failed. Answer without it and say so.")

    assert evidence.figures == {}
    assert EVIDENCE.views == {"c2": ViewScope.MINE, "c3": None}
    assert {3, 2, 5} <= EVIDENCE.counts


# ── properties ────────────────────────────────────────────────────────────────


def _one(ref: str, unit: render.Unit, value: int) -> Evidence:
    shown = render.display(unit, value)
    return Evidence(figures={ref: Figure(ref=ref, unit=unit, value=value, display=shown)})


@given(st.integers(min_value=-(10**13), max_value=10**13))
def test_every_money_form_render_produces_is_matched(cents: int) -> None:
    evidence = _one("c1.x", "cents", cents)

    assert [f.status for f in check(render.money(cents), evidence).figures] == [
        FigureStatus.MATCHED
    ]


@given(st.integers(min_value=-(10**13), max_value=10**13), st.sampled_from([-1, 1]))
def test_money_one_cent_off_is_not(cents: int, off: int) -> None:
    evidence = _one("c1.x", "cents", cents)

    assert [f.status for f in check(render.money(cents + off), evidence).figures] == [
        FigureStatus.UNVERIFIED
    ]


@given(st.integers(min_value=-(10**6), max_value=10**6), st.sampled_from([-1, 0, 1]))
def test_percentages_match_exactly_and_one_basis_point_off_does_not(bps: int, off: int) -> None:
    evidence = _one("c1.x", "bps", bps)
    expected = FigureStatus.MATCHED if off == 0 else FigureStatus.UNVERIFIED

    assert [f.status for f in check(render.percent(bps + off), evidence).figures] == [expected]


@given(st.integers(min_value=1, max_value=10**5), st.sampled_from([-1, 0, 1]))
def test_months_match_exactly_and_one_tenth_off_does_not(tenths: int, off: int) -> None:
    evidence = _one("c1.x", "months_tenths", tenths)
    expected = FigureStatus.MATCHED if off == 0 else FigureStatus.UNVERIFIED

    assert [f.status for f in check(render.months(tenths + off), evidence).figures] == [expected]


@given(
    st.sampled_from(["cents", "bps", "months_tenths"]),
    st.integers(min_value=-(10**12), max_value=10**12),
)
def test_a_reference_resolves_to_exactly_its_canonical_form(unit: render.Unit, value: int) -> None:
    evidence = _one("c4.buckets.3.change", unit, value)

    checked = check("{{c4.buckets.3.change}}", evidence)

    assert checked.text == render.display(unit, value)
    assert [f.status for f in checked.figures] == [FigureStatus.VERIFIED]


# ── streaming ─────────────────────────────────────────────────────────────────

STREAMED = "Net worth {{c2.net_worth}} {mine}, {{c9.gone}} and {{ c2.change_pct }}{"


def test_a_reference_split_across_chunks_is_held_until_complete() -> None:
    resolver = StreamResolver(EVIDENCE)

    assert resolver.feed("Net worth: {{c2.net") == "Net worth: "
    assert resolver.feed("_worth}} today") == "$1,234.56 today"
    assert resolver.flush() == ""


@pytest.mark.parametrize("cut", range(len(STREAMED) + 1))
def test_every_split_point_streams_the_same_text(cut: int) -> None:
    resolver = StreamResolver(EVIDENCE)

    streamed = resolver.feed(STREAMED[:cut]) + resolver.feed(STREAMED[cut:]) + resolver.flush()

    assert streamed == "Net worth $1,234.56 {mine}, {{c9.gone}} and 12.34%{"


def test_character_by_character_streaming_matches_the_final_check() -> None:
    resolver = StreamResolver(EVIDENCE)

    streamed = "".join(resolver.feed(ch) for ch in STREAMED) + resolver.flush()

    assert streamed == check(STREAMED, EVIDENCE).text


# ── policy checks ─────────────────────────────────────────────────────────────


def _policy(text: str, names: tuple[str, ...] = ()) -> list[PolicyCheck]:
    checked = check(text, EVIDENCE)
    notes = policy.check(
        checked.text, figures=checked.figures, evidence=EVIDENCE, exempt_names=names
    )
    return [n.check for n in notes]


@pytest.mark.parametrize(
    ("text", "names", "failed"),
    [
        ("Consider a broad US total-market index fund.", (), []),
        ("Consider VTI for the long run.", (), [PolicyCheck.TICKER_OR_ISSUER]),
        ("VTSAX is a common choice.", (), [PolicyCheck.TICKER_OR_ISSUER]),
        ("A Vanguard fund would do.", (), [PolicyCheck.TICKER_OR_ISSUER]),
        ("Your Fidelity brokerage is stale.", ("Fidelity Investments",), []),
        ("Your Fidelity brokerage is stale.", (), [PolicyCheck.TICKER_OR_ISSUER]),
        ("I've marked the credit as used.", (), [PolicyCheck.CLAIMED_ACTION]),
        ("I moved $500 to savings.", (), [PolicyCheck.CLAIMED_ACTION]),
        ("Done.\nAnything else?", (), [PolicyCheck.CLAIMED_ACTION]),
        ("I looked up your cards. Mark it used on [[screen:cards]].", (), []),
        ("The 401(k) contribution limit is $23,500.", (), [PolicyCheck.TAX_FIGURE]),
        ("You are in the 22% tax bracket.", (), [PolicyCheck.TAX_FIGURE]),
        ("Check this year's IRA contribution limit with the IRS.", (), []),
        ("Household net worth is {{c2.net_worth}}.", (), []),
        ("Mine: {{c2.net_worth}}.", (), []),
        ("Net worth is {{c2.net_worth}}.", (), [PolicyCheck.SCOPE_LABEL]),
        ("Spending was {{c3.total}}.", (), []),
        ("Your share of groceries was {{c3.total}}.", (), [PolicyCheck.SCOPE_LABEL]),
        ("Alex's share of the spending is high.", (), [PolicyCheck.SCOPE_LABEL]),
    ],
)
def test_each_policy_check_passes_and_fails(
    text: str, names: tuple[str, ...], failed: list[PolicyCheck]
) -> None:
    assert _policy(text, names) == failed


def test_a_grounded_figure_in_a_tax_sentence_is_not_a_tax_figure() -> None:
    assert _policy("Your 401(k) balance is {{c2.net_worth}} (Mine), below any limit.") == []


def test_household_names_come_from_institutions_and_accounts(
    db_session: Session, make_account: Any
) -> None:
    make_account(name="Fidelity Brokerage")

    names = policy.household_names(db_session)

    assert {"Fidelity Brokerage", "Institution Fidelity Brokerage"} <= names


# ── post-processing ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("See [the docs](https://evil.example/x).", "See the docs."),
        ("See [the docs][1].\n\n[1]: https://evil.example/x", "See the docs.\n\n"),
        ("![chart](https://evil.example/p.png?d=1)done", "done"),
        ('![x][1]\n[1]: https://evil.example/p.png "t"\nok', "\nok"),
        ("![x][img]\n  [img]: <https://evil.example/p.png>\nok", "\nok"),
        ("<https://evil.example/a>", ""),
        ("<img src=x onerror=alert(1)>hi", "hi"),
        ("<b>bold</b>", "bold"),
        ("a<!-- secret -->b", "ab"),
        ("go to https://evil.example/x?d=1 now", "go to [link removed] now"),
        ("or www.evil.example", "or [link removed]"),
        ("or evil.com/steal", "or [link removed]"),
        ("Open [[screen:cards]].", "Open [[screen:cards]]."),
        ("Open [[screen:bank]].", "Open ."),
        ("Keep {{c2.net_worth}} and **bold**.", "Keep {{c2.net_worth}} and **bold**."),
        ("Spent < $100 and > $50.", "Spent < $100 and > $50."),
    ],
)
def test_links_images_and_html_are_stripped(raw: str, shown: str) -> None:
    assert answer.clean(raw) == shown


def test_nothing_url_shaped_survives_the_echoleak_shapes() -> None:
    raw = (
        "Summary ![a][r1] and [b][r2] and [c][].\n"
        "[r1]: https://attacker.example/x.png?q=secret\n"
        "[r2]: http://attacker.example/\n"
        "[c]: //attacker.example\n"
    )

    cleaned = answer.clean(raw)

    assert "attacker" not in cleaned
    assert "![" not in cleaned


# ── the loop ──────────────────────────────────────────────────────────────────


REGISTRY = load_all()


@pytest.fixture
def run(db_session: Session, owner_id: int) -> Any:
    store = Store(nested_in(db_session))
    conversation = store.create_conversation(owner_id, "mine", "q", NOW)

    def go(client: ScriptedModelClient, question: str = "Net worth?") -> list[dict[str, Any]]:
        deps = TurnDeps(
            client=client,
            store=store,
            registry=REGISTRY,
            tool_sessions=savepoint_read_only(db_session),
            settings=Settings(
                database_url="postgresql://unused",
                advisor_enabled=True,
                anthropic_api_key=SecretStr("test-key-not-real"),
            ),
            now=lambda: NOW,
        )

        async def collect() -> list[dict[str, Any]]:
            stream = run_turn(
                deps,
                conversation_id=conversation,
                user_id=owner_id,
                view=ViewScope.MINE,
                question=question,
            )
            return [e.model_dump(mode="json") async for e in stream]

        return asyncio.run(collect())

    go.conversation = conversation  # type: ignore[attr-defined]
    go.db = db_session  # type: ignore[attr-defined]
    return go


def _turn(run: Any) -> AdvisorTurn:
    run.db.expire_all()
    turn: AdvisorTurn = run.db.query(AdvisorTurn).filter_by(conversation_id=run.conversation).one()
    return turn


def _lookup_then(*answers: ScriptedCall) -> ScriptedModelClient:
    return ScriptedModelClient(
        [ScriptedCall(tool_calls=[ToolUse("t1", "networth_get", {"view": None})]), *answers]
    )


def test_references_are_written_in_as_the_answer_streams(run: Any) -> None:
    client = _lookup_then(ScriptedCall(text=["Mine: {{c1.net", "_worth}}."]))

    events = run(client)

    deltas = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert deltas == "Mine: $0.00."
    (answer_event,) = [e["answer"] for e in events if e["type"] == "answer"]
    assert answer_event["text"] == "Mine: $0.00."
    assert [f["status"] for f in answer_event["figures"]] == ["verified"]
    assert events[-1]["grounding"] == "verified"
    assert _turn(run).grounding == "verified"


def test_an_unverified_figure_gets_one_regeneration(run: Any) -> None:
    def told_what_failed(request: ModelRequest) -> None:
        note = request.messages[-1]["content"][-1]["text"]
        assert "$5.00" in note
        assert "{{c2.net_worth}}" in note

    client = _lookup_then(
        ScriptedCall(text=["Mine: about $5.00."]),
        ScriptedCall(text=["Mine: {{c1.net_worth}}."], expect=told_what_failed),
    )

    events = run(client)

    kinds = [e["type"] for e in events]
    assert kinds.count("regenerating") == 1
    assert kinds.index("regenerating") < kinds.index("answer")
    final = next(e["answer"] for e in events if e["type"] == "answer")
    assert final["text"] == "Mine: $0.00."
    assert events[-1]["grounding"] == "verified"


def test_a_second_failure_ships_marked_and_flagged(run: Any) -> None:
    client = _lookup_then(
        ScriptedCall(text=["Mine: about $5.00."]),
        ScriptedCall(text=["Mine: still $5.00. I've marked it done."]),
    )

    events = run(client)

    final = next(e["answer"] for e in events if e["type"] == "answer")
    assert [f["status"] for f in final["figures"]] == ["unverified"]
    assert [n["check"] for n in final["policy_notes"]] == ["claimed_action"]
    assert events[-1]["grounding"] == "flagged"
    assert _turn(run).grounding == "flagged"
    assert len(client.requests) == 3  # the lookup, the answer, one regeneration — no more


def test_a_policy_failure_alone_gets_the_retry(run: Any) -> None:
    client = ScriptedModelClient(
        [
            ScriptedCall(text=["Buy VTI."]),
            ScriptedCall(text=["Consider a broad total-market index fund."]),
        ]
    )

    events = run(client)

    regenerating = next(e for e in events if e["type"] == "regenerating")
    assert "rules" in regenerating["reason"]
    final = next(e["answer"] for e in events if e["type"] == "answer")
    assert final["policy_notes"] == []
    assert events[-1]["grounding"] == "none"


def test_limitations_and_sources_come_from_the_tool_calls(run: Any) -> None:
    client = ScriptedModelClient(
        [
            ScriptedCall(
                tool_calls=[
                    ToolUse("t1", "networth_get", {"view": None}),
                    ToolUse("t2", "note_limitation", {"capability": "holdings"}),
                    ToolUse("t3", "note_limitation", {"capability": "holdings"}),
                ]
            ),
            ScriptedCall(text=["The app has no holdings, so I can't say."]),
        ]
    )

    events = run(client)

    final = next(e["answer"] for e in events if e["type"] == "answer")
    assert final["limitations"] == ["holdings"]
    assert [c["tool"] for c in final["citations"]] == ["networth_get"]
    assert final["citations"][0]["view"] == "mine"


def test_links_never_reach_the_answer(run: Any) -> None:
    client = ScriptedModelClient(
        [ScriptedCall(text=["See ![x][1] and [[screen:cards]].\n[1]: https://evil.example/a"])]
    )

    final = next(e["answer"] for e in run(client) if e["type"] == "answer")

    assert "evil" not in final["text"]
    assert "[[screen:cards]]" in final["text"]


def test_a_figure_from_an_earlier_turn_still_resolves(run: Any) -> None:
    run(_lookup_then(ScriptedCall(text=["Mine: {{c1.net_worth}}."])))
    later = ScriptedModelClient([ScriptedCall(text=["Still (Mine) {{c1.net_worth}}."])])

    events = run(later, question="And now?")

    final = next(e["answer"] for e in events if e["type"] == "answer")
    assert [f["status"] for f in final["figures"]] == ["verified"]


def test_grounding_module_says_what_it_does_not_prove() -> None:
    assert grounding.__doc__ is not None
    assert "does not" in grounding.__doc__
    assert "prove" in grounding.__doc__


def test_note_limitation_is_registered_with_the_limitation_enum() -> None:
    schema = next(d for d in REGISTRY.definitions() if d.name == "note_limitation").input_schema

    assert "market_data" in schema["properties"]["capability"]["enum"]
