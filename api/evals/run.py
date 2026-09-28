"""`make eval`: ask the golden questions of a real model, grade every answer, print the cost.

docs/ADVISOR.md#make-eval. The release gate for switching the advisor on, and for every later
change of model, effort, prompt or tool schema. **Never run in CI** — a test holds that line.

- **The world** is a database of its own, `pfa_eval` on the local Postgres: created if
  missing, migrated, then rebuilt from the seed and the overlay on every run. The development
  database is never touched.
- **The provider** is `local` (ticket 120's adapter — free, the default while building) or
  `anthropic` with the **eval key**, `EVAL_ANTHROPIC_API_KEY`, from the `pfa-eval` workspace
  with its own spend limit. Never the production key.
- `n=` repeats each case, `only=` filters by category or case id, and `max_cost=` (dollars,
  default 10) stops the run cleanly before the next case once spend reaches it.
- **Output:** a per-case table, pass rates per category against the thresholds, tokens by
  class, cost, and a non-zero exit below any threshold. A JSON report — every answer, for
  `make eval-label` and `make eval-examples` — goes to `data/evals/`, which is gitignored.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import statistics
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.advisor import pricing
from app.advisor.loop import TurnDeps, prompt_version, run_turn
from app.advisor.model import (
    AnthropicModelClient,
    Effort,
    ModelClient,
    ModelRequest,
    ModelResponse,
    TextDelta,
    Usage,
)
from app.advisor.model_local import LocalModelClient
from app.advisor.store import Store
from app.advisor.tools import SessionScope, load_all
from app.config import Settings
from app.models.advisor import AdvisorUsage
from app.models.user import User
from app.schemas.common import ViewScope
from evals import EVAL_TODAY, Case, load_cases, load_expected
from evals.graders import (
    ADVICE_MEAN_TENTHS,
    CALIBRATION_MIN_PCT,
    MEDIAN_COST_CENTS,
    CategoryResult,
    Result,
    RubricError,
    RubricScore,
    agreement_pct,
    by_category,
    grade,
    parse_rubric,
    rubric_request,
)

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "data" / "evals"
LABELS = REPORTS / "labels.json"
DEFAULT_EVAL_DB = "postgresql+psycopg://pfa:pfa_local_dev@localhost:5432/pfa_eval"
ADVICE = "goal_aware"
TOKEN_CLASSES = (
    "input_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "cache_read_tokens",
    "output_tokens",
)


@dataclass
class Run:
    case_id: str
    category: str
    repeat: int
    question: str
    passed: bool
    failures: list[str]
    verified: int
    matched: int
    unverified: int
    tools: list[str]
    cost_cents: Decimal
    tokens: dict[str, int]
    answer: dict[str, Any] | None
    lookups: list[dict[str, Any]]
    error: str | None
    rubric: dict[str, int] | None = None
    rubric_mean_tenths: int | None = None


@dataclass
class Report:
    provider: str
    model: str
    effort: str
    n: int
    only: str | None
    max_cost_cents: Decimal
    runs: list[Run] = field(default_factory=list)
    aborted: bool = False
    calibration_pct: int | None = None
    calibration_labels: int = 0
    #: What re-grading the labelled answers cost; counted in the total.
    calibration_cost_cents: Decimal = Decimal(0)

    @property
    def cost_cents(self) -> Decimal:
        return sum((r.cost_cents for r in self.runs), self.calibration_cost_cents)

    @property
    def categories(self) -> list[CategoryResult]:
        return by_category((r.category, r.passed) for r in self.runs)

    @property
    def ungrounded(self) -> int:
        strict = {"lookup", "comparison", "trend", "multi_hop"}
        return sum(r.unverified for r in self.runs if r.category in strict)

    @property
    def median_cost_cents(self) -> Decimal:
        costs = [r.cost_cents for r in self.runs]
        return statistics.median(costs) if costs else Decimal(0)

    @property
    def advice_mean_tenths(self) -> int | None:
        means = [r.rubric_mean_tenths for r in self.runs if r.rubric_mean_tenths is not None]
        if not means:
            return None
        return int(Decimal(sum(means)) / len(means))

    @property
    def advice_trusted(self) -> bool:
        return self.calibration_pct is not None and self.calibration_pct >= CALIBRATION_MIN_PCT

    def gate(self) -> list[str]:
        """Every threshold missed. Empty means the gate passed."""
        missed = [
            f"{c.category}: {c.rate} (needs {c.threshold_pct}%)"
            for c in self.categories
            if not c.ok
        ]
        if self.ungrounded:
            missed.append(f"{self.ungrounded} ungrounded figure(s) in graded categories")
        mean = self.advice_mean_tenths
        if mean is not None and mean < ADVICE_MEAN_TENTHS:
            missed.append(f"advice rubric mean {Decimal(mean).scaleb(-1)} (needs 4.0)")
        if self.provider != "local" and self.median_cost_cents > MEDIAN_COST_CENTS:
            missed.append(f"median cost {_format_cents(self.median_cost_cents)} per case")
        if self.aborted:
            missed.append("stopped at max_cost before every case ran")
        return missed


def _format_cents(cents: Decimal) -> str:
    whole = pricing.display_cents(cents)
    return f"${whole // 100:,}.{whole % 100:02d}"


# ── the eval database ─────────────────────────────────────────────────────────


def prepare_database(url: str) -> None:
    """Create `pfa_eval` if needed, migrate it, and rebuild the world in it."""
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from alembic import command
    from evals import overlay

    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": target.database}
        ).first()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()

    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = url
    command.upgrade(config, "head")

    engine = create_engine(url)
    with Session(engine) as session, session.begin():
        # Last run's conversations and spend would count against this run's caps.
        session.execute(
            text(
                "TRUNCATE advisor_usage, advisor_tool_calls, advisor_messages, "
                "advisor_turns, advisor_conversations"
            )
        )
        overlay.build(session)
    engine.dispose()


def use_database(url: str) -> None:
    """Point the app's own sessions at `url`, as the loop in production would use them."""
    from app.config import get_settings
    from app.db import get_engine, get_sessionmaker

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


# ── providers ─────────────────────────────────────────────────────────────────


def make_client(provider: str, model: str, effort: Effort, max_tokens: int) -> ModelClient:
    if provider == "anthropic":
        key = os.environ.get("EVAL_ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit(
                "EVAL_ANTHROPIC_API_KEY is not set. Evals use the pfa-eval workspace's key, "
                "never the production one."
            )
        return AnthropicModelClient(api_key=key, model=model, effort=effort, max_tokens=max_tokens)
    if provider == "local":
        settings = Settings(database_url=os.environ.get("DATABASE_URL", "postgresql://unused"))
        return LocalModelClient(
            base_url=settings.local_model_url, model=settings.local_model, max_tokens=max_tokens
        )
    raise SystemExit(f"unknown provider {provider!r}: use local or anthropic")


def eval_settings(max_cost_cents: Decimal, max_tokens: int) -> Settings:
    """The advisor's settings for an eval run: on, and capped at the run's own budget."""
    cap = max(1, int(max_cost_cents))
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "postgresql://unused"),
        advisor_enabled=True,
        anthropic_api_key=SecretStr("eval"),
        advisor_max_tokens=max_tokens,
        advisor_monthly_cap_cents=cap,
        advisor_conversation_cap_cents=cap,
    )


# ── running ───────────────────────────────────────────────────────────────────


@dataclass
class Runner:
    client: ModelClient
    store: Store
    tool_sessions: SessionScope
    transaction: Callable[[], AbstractContextManager[Session]]
    settings: Settings
    facts: dict[str, dict[str, Any]]
    rubric_client: ModelClient | None = None

    def _owner(self) -> int:
        with self.transaction() as session:
            return int(session.execute(select(User.id).order_by(User.id)).scalars().first() or 0)

    def _usage(self, turn_id: uuid.UUID) -> dict[str, int]:
        with self.transaction() as session:
            rows = session.execute(
                select(AdvisorUsage).where(AdvisorUsage.turn_id == turn_id)
            ).scalars()
            totals = dict.fromkeys(TOKEN_CLASSES, 0)
            for row in rows:
                for name in TOKEN_CLASSES:
                    totals[name] += getattr(row, name)
            return totals

    async def run_case(self, case: Case, repeat: int) -> Run:
        now = dt.datetime.combine(EVAL_TODAY, dt.time(12), tzinfo=dt.UTC)
        owner = self._owner()
        conversation = self.store.create_conversation(owner, case.scope, "", now)
        deps = TurnDeps(
            client=self.client,
            store=self.store,
            registry=load_all(),
            tool_sessions=self.tool_sessions,
            settings=self.settings,
            now=lambda: now,
        )
        events = [
            event.model_dump(mode="json")
            async for event in run_turn(
                deps,
                conversation_id=conversation,
                user_id=owner,
                view=ViewScope(case.scope),
                question=case.question,
            )
        ]
        result = Result.from_events(events)
        graded = grade(case, result, self.facts)
        started = next((e for e in events if e["type"] == "turn_started"), None)
        turn_id = uuid.UUID(started["turn_id"]) if started else None
        cost = self.store.turn_spent(turn_id) if turn_id else Decimal(0)
        tokens = self._usage(turn_id) if turn_id else dict.fromkeys(TOKEN_CLASSES, 0)
        answer = next((e["answer"] for e in events if e["type"] == "answer"), None)
        run = Run(
            case_id=case.id,
            category=case.category,
            repeat=repeat,
            question=case.question,
            passed=graded.passed,
            failures=graded.failures,
            verified=graded.verified,
            matched=graded.matched,
            unverified=graded.unverified,
            tools=result.tools,
            cost_cents=cost,
            tokens=tokens,
            answer=answer,
            lookups=[e["lookup"] for e in events if e["type"] == "tool_call"],
            error=result.error,
        )
        if case.category == ADVICE and answer is not None and self.rubric_client is not None:
            score, spent = await score_rubric(self.rubric_client, case.question, answer["text"])
            run.cost_cents += spent
            if score is None:
                run.failures.append("rubric: the grader's reply was unusable")
                run.passed = False
            else:
                run.rubric = score.scores
                run.rubric_mean_tenths = score.mean_tenths
                if not score.passed:
                    run.failures.append(f"rubric mean {Decimal(score.mean_tenths).scaleb(-1)}")
                    run.passed = False
        return run

    async def run(self, report: Report, cases: list[Case]) -> Report:
        for case in cases:
            for repeat in range(report.n):
                if report.cost_cents >= report.max_cost_cents:
                    report.aborted = True
                    return report
                report.runs.append(await self.run_case(case, repeat))
        return report


async def score_rubric(
    client: ModelClient, question: str, answer: str
) -> tuple[RubricScore | None, Decimal]:
    """The rubric grader's scores for one answer, and what grading it cost."""
    system, messages = rubric_request(question, answer)
    text_parts: list[str] = []
    usage = Usage()
    model = client.model
    async for event in client.stream(ModelRequest(system=system, messages=messages, tools=[])):
        if isinstance(event, TextDelta):
            text_parts.append(event.text)
        elif isinstance(event, ModelResponse):
            usage, model = event.usage, event.model
    cost = pricing.cost_cents(usage, model, EVAL_TODAY, provider=client.provider)
    try:
        return parse_rubric("".join(text_parts)), cost
    except RubricError:
        return None, cost


def label_key(case_id: str, answer: str) -> str:
    return f"{case_id}:{hashlib.sha256(answer.encode()).hexdigest()[:16]}"


async def calibrate(report: Report, client: ModelClient, labels: list[dict[str, Any]]) -> None:
    """Re-grade every labelled answer with the rubric and record how often it agreed."""
    pairs: list[tuple[bool, bool]] = []
    for label in labels:
        score, spent = await score_rubric(client, label["question"], label["answer"])
        report.calibration_cost_cents += spent
        if score is not None:
            pairs.append((score.passed, label["label"] == "pass"))
    report.calibration_pct = agreement_pct(pairs)
    report.calibration_labels = len(pairs)


# ── output ────────────────────────────────────────────────────────────────────


def select_cases(only: str | None) -> list[Case]:
    cases = [c for c in load_cases() if c.pending is None]
    if only:
        wanted = {w.strip() for w in only.split(",")}
        cases = [c for c in cases if c.category in wanted or c.id in wanted]
    return cases


def render_table(report: Report) -> Iterator[str]:
    yield f"{'case':<28} {'cat':<12} {'ok':<4} {'v/m/u':<8} {'tools':<5} {'cost':>8}  notes"
    for r in report.runs:
        mark = "pass" if r.passed else "FAIL"
        vmu = f"{r.verified}/{r.matched}/{r.unverified}"
        note = "; ".join(r.failures)[:70]
        yield (
            f"{r.case_id:<28} {r.category:<12} {mark:<4} {vmu:<8} {len(r.tools):<5} "
            f"{_format_cents(r.cost_cents):>8}  {note}"
        )
    yield ""
    yield f"{'category':<14} {'runs':>5} {'passed':>7} {'rate':>7} {'needs':>6}"
    for c in report.categories:
        needs = f"{c.threshold_pct}%" if c.threshold_pct is not None else "—"
        flag = "" if c.ok else "  ← below"
        yield f"{c.category:<14} {c.runs:>5} {c.passed:>7} {c.rate:>7} {needs:>6}{flag}"
    yield ""
    totals = dict.fromkeys(TOKEN_CLASSES, 0)
    for r in report.runs:
        for name in TOKEN_CLASSES:
            totals[name] += r.tokens.get(name, 0)
    yield "tokens: " + ", ".join(f"{k.removesuffix('_tokens')} {v:,}" for k, v in totals.items())
    yield (
        f"cost: {_format_cents(report.cost_cents)} total, "
        f"{_format_cents(report.median_cost_cents)} median per case "
        f"({report.provider}, {report.model}, effort {report.effort})"
    )
    yield f"ungrounded figures in graded categories: {report.ungrounded}"
    if report.advice_mean_tenths is not None:
        trust = "trusted" if report.advice_trusted else "UNTRUSTED — calibrate with make eval-label"
        yield (
            f"advice rubric mean: {Decimal(report.advice_mean_tenths).scaleb(-1)} "
            f"(agreement {report.calibration_pct}% over {report.calibration_labels} labels; "
            f"{trust})"
        )


def to_json(report: Report) -> dict[str, Any]:
    return {
        "ran_at": dt.datetime.now(dt.UTC).isoformat(),
        "provider": report.provider,
        "model": report.model,
        "effort": report.effort,
        "prompt_version": prompt_version(),
        "n": report.n,
        "only": report.only,
        "max_cost_cents": str(report.max_cost_cents),
        "cost_cents": str(report.cost_cents),
        "median_cost_cents": str(report.median_cost_cents),
        "ungrounded": report.ungrounded,
        "aborted": report.aborted,
        "calibration_pct": report.calibration_pct,
        "gate": report.gate(),
        "categories": [
            {"category": c.category, "runs": c.runs, "passed": c.passed, "ok": c.ok}
            for c in report.categories
        ],
        "runs": [{**run.__dict__, "cost_cents": str(run.cost_cents)} for run in report.runs],
    }


def write_report(report: Report, directory: Path = REPORTS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"eval-{stamp}.json"
    path.write_text(json.dumps(to_json(report), indent=2) + "\n", encoding="utf-8")
    return path


def latest_report(directory: Path = REPORTS) -> dict[str, Any]:
    reports = sorted(directory.glob("eval-*.json"))
    if not reports:
        raise SystemExit(f"No eval report in {directory}. Run `make eval` first.")
    data: dict[str, Any] = json.loads(reports[-1].read_text(encoding="utf-8"))
    return data


def load_labels(path: Path = LABELS) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    labels: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return labels


# ── the command ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--provider", default="local", choices=["local", "anthropic"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--only", default=None)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal(10), help="dollars")
    parser.add_argument(
        "--database-url", default=os.environ.get("EVAL_DATABASE_URL", DEFAULT_EVAL_DB)
    )
    args = parser.parse_args(argv)

    defaults = Settings(database_url=args.database_url)
    model = args.model or defaults.advisor_model
    effort: Effort = args.effort or defaults.advisor_effort
    max_cost_cents = args.max_cost * 100

    client = make_client(args.provider, model, effort, defaults.advisor_max_tokens)
    prepare_database(args.database_url)
    use_database(args.database_url)

    from app.advisor.store import fresh_transaction
    from app.advisor.tools import fresh_read_only_session

    report = Report(
        provider=args.provider,
        model=client.model,
        effort=effort,
        n=args.n,
        only=args.only,
        max_cost_cents=max_cost_cents,
    )
    runner = Runner(
        client=client,
        store=Store(fresh_transaction),
        tool_sessions=fresh_read_only_session,
        transaction=fresh_transaction,
        settings=eval_settings(max_cost_cents, defaults.advisor_max_tokens),
        facts=load_expected()["facts"],
        rubric_client=client,
    )
    cases = select_cases(args.only)
    asyncio.run(runner.run(report, cases))
    if any(r.rubric is not None for r in report.runs):
        asyncio.run(calibrate(report, client, load_labels()))

    for line in render_table(report):
        print(line)
    path = write_report(report)
    print(f"report: {path.relative_to(REPO)}")
    missed = report.gate()
    if missed:
        print("GATE FAILED:\n  " + "\n  ".join(missed), file=sys.stderr)
        return 1
    print("gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
