"""The advisor's tools: a fixed registry of read-only, bounded, audited lookups.

SECURITY.md#ai-agent fixes the rules, and this module is where they are enforced rather
than remembered:

- **A fixed set.** A tool is a Python function registered here with a Pydantic argument
  model and a Pydantic result model. The schema a model sees is generated from the
  argument model; nothing that is not registered can be called.
- **Read-only by construction.** Every call runs in a transaction set `READ ONLY` with a
  statement timeout, so a write fails at the database rather than depending on the
  function having been written carefully.
- **Bounded.** Arguments are validated here whatever the provider promised; every call,
  row and rendered byte counts against the turn's budget.
- **Audited.** Every call — valid, invalid, failed or refused — reaches the audit sink with
  its validated arguments.

See docs/ADVISOR.md#tools.
"""

from __future__ import annotations

import copy
import datetime as dt
import enum
import re
import time
import typing
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.advisor import render as render_module
from app.logging import get_logger
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope
from app.services.analysis.periods import MAX_DAYS, PeriodError, PeriodPreset, Window
from app.services.analysis.periods import resolve as resolve_period

logger = get_logger("advisor.tools")

#: How long one tool call may run in the database before Postgres cancels it.
STATEMENT_TIMEOUT_MS = 5_000

#: Area prefixes a tool name may start with. Namespaced so related tools sort together
#: and the right one is easy to pick (Anthropic's tool-writing guidance).
NAMESPACES = frozenset(
    {
        "networth",
        "accounts",
        "runway",
        "spend",
        "transactions",
        "cashflow",
        "categories",
        "rules",
        "cards",
        "data",
        "findings",
        "goals",
        "planning",
        "debt",
        "allocation",
        "projection",
        "note",
    }
)

#: The one argument allowed to carry free text. Its pattern cannot express a URL.
FREE_TEXT_ARGUMENTS = frozenset({"merchant_query"})


#: An id argument. Bounded like every integer a model may send (see `lint_args_model`).
Id = Annotated[int, Field(ge=1, le=2_147_483_647)]


class ToolArgs(BaseModel):
    """Base for every tool's arguments: no extra fields, immutable once validated."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NoArgs(ToolArgs):
    """For a tool that takes no arguments."""


class ToolResult(BaseModel):
    """Base for every tool's result. `as_of`, `view` and `stale` become the envelope.

    Money is `*_cents`, percentages `*_bps`, months `*_months_tenths`; untrusted text is
    `*_text`. `render.py` refuses a float or a Decimal.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: dt.date | None = None
    view: ViewScope | None = None
    stale: bool | None = None

    def row_count(self) -> int:
        """Rows this result returns, for the turn's row budget. Aggregates return none."""
        return 0


class Detail(enum.StrEnum):
    """How much a larger tool returns. `concise` leaves out per-item breakdowns."""

    CONCISE = "concise"
    FULL = "full"


class PeriodArg(ToolArgs):
    """A calendar period. Presets resolve in `services/analysis/periods.py`."""

    preset: PeriodPreset = Field(
        description=(
            "A calendar-aligned period relative to today. Use custom only for dates the "
            "user named, and then give both start and end."
        )
    )
    start: dt.date | None = Field(default=None, description="custom only: the first day.")
    end: dt.date | None = Field(default=None, description="custom only: the last day.")

    def resolve(self, today: dt.date, max_days: int = MAX_DAYS) -> Window:
        return resolve_period(self.preset, today, self.start, self.end, max_days)


class ToolInputError(ValueError):
    """Arguments that validated but make no sense for today — a future date, say.

    Raised by a tool; returned to the model as an `invalid_args` result with this message.
    """


@dataclass
class TurnBudget:
    """What one turn may consume. Checked before each call; charged after."""

    max_calls: int = 12
    max_rows: int = 100
    max_bytes: int = 40_000
    calls: int = 0
    rows: int = 0
    bytes: int = 0

    def take_call(self) -> bool:
        if self.calls >= self.max_calls:
            return False
        self.calls += 1
        return True

    def take(self, rows: int, size: int) -> bool:
        if self.rows + rows > self.max_rows or self.bytes + size > self.max_bytes:
            return False
        self.rows += rows
        self.bytes += size
        return True


SessionScope = Callable[[], AbstractContextManager[Session]]


def _read_only(session: Session, timeout_ms: int) -> None:
    session.execute(text("SET TRANSACTION READ ONLY"))
    session.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))


@contextmanager
def fresh_read_only_session(timeout_ms: int = STATEMENT_TIMEOUT_MS) -> Iterator[Session]:
    """Production: a new session, its transaction read-only, rolled back afterwards."""
    from app.db import get_sessionmaker

    with get_sessionmaker()() as session:
        _read_only(session, timeout_ms)
        try:
            yield session
        finally:
            session.rollback()


def savepoint_read_only(session: Session, timeout_ms: int = STATEMENT_TIMEOUT_MS) -> SessionScope:
    """Tests: a read-only savepoint inside an existing session, rolled back afterwards.

    The suite's session is joined to an outer transaction rolled back per test (ADR 0005),
    so a fresh session would not see fixture rows. Postgres lets a savepoint be switched
    to read-only, and rolling the savepoint back restores read-write — checked against
    Postgres before this was written, and pinned by `test_advisor_framework.py`.
    """

    @contextmanager
    def scope() -> Iterator[Session]:
        nested = session.begin_nested()
        _read_only(session, timeout_ms)
        try:
            yield session
        finally:
            nested.rollback()

    return scope


@dataclass(frozen=True)
class ToolOutcome:
    """One call, as the loop, the audit log and the "show lookups" control need it."""

    call_id: str
    tool: str
    label: str
    status: LookupStatus
    #: What goes back to the model: the rendering, or an error it can act on.
    content: str
    figures: dict[str, render_module.Figure]
    row_count: int
    latency_ms: int
    withheld_count: int
    arguments: str
    #: Validated arguments, JSON-able, for the audit table. Never results.
    args: dict[str, Any]
    as_of: dt.date | None = None
    view: ViewScope | None = None
    stale: bool = False
    #: The exception class when a call failed. Never its message, which could hold values.
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.status is not LookupStatus.OK


class AuditSink(Protocol):
    def record(self, outcome: ToolOutcome) -> None: ...


@dataclass
class MemoryAudit:
    """An audit sink that keeps outcomes in a list. The loop's database sink is 097's."""

    outcomes: list[ToolOutcome] = field(default_factory=list)

    def record(self, outcome: ToolOutcome) -> None:
        self.outcomes.append(outcome)


@dataclass
class CallIds:
    """`c1`, `c2`, … — unique across a conversation, so references from earlier turns hold."""

    issued: int = 0

    def next(self) -> str:
        self.issued += 1
        return f"c{self.issued}"


@dataclass
class ToolContext:
    """Everything a tool may know about the turn. No tool reads the clock or the request."""

    today: dt.date
    user_id: int
    view: ViewScope
    sessions: SessionScope
    budget: TurnBudget = field(default_factory=TurnBudget)
    audit: AuditSink = field(default_factory=MemoryAudit)
    call_ids: CallIds = field(default_factory=CallIds)

    def viewer_id(self, view: ViewScope | None = None) -> int | None:
        """Whose stake applies: this user's for `mine`, every stake for `household`."""
        chosen = view or self.view
        return None if chosen is ViewScope.HOUSEHOLD else self.user_id


A = TypeVar("A", bound=ToolArgs)
R = TypeVar("R", bound=ToolResult)
ToolFn = Callable[[A, Session, ToolContext], R]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    fn: Callable[[Any, Session, ToolContext], ToolResult]
    shape: Literal["aggregate", "rows"]
    label: Callable[[Any], str]


@dataclass(frozen=True)
class ToolDefinition:
    """A tool as a model provider sees it. Each client adds its own flags (`strict`)."""

    name: str
    description: str
    input_schema: dict[str, Any]


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def tool(
        self,
        name: str,
        *,
        description: str,
        shape: Literal["aggregate", "rows"] = "aggregate",
        label: Callable[[Any], str] | None = None,
    ) -> Callable[[ToolFn[A, R]], ToolFn[A, R]]:
        """Register a function as a tool. Its first parameter's type is its argument model."""

        def register(fn: ToolFn[A, R]) -> ToolFn[A, R]:
            if name in self._tools:
                raise ValueError(f"tool {name!r} registered twice")
            hints = typing.get_type_hints(fn)
            args_model = next(iter(hints.values()))
            if not (isinstance(args_model, type) and issubclass(args_model, ToolArgs)):
                raise TypeError(f"{name}: first parameter must be a ToolArgs subclass")
            self._tools[name] = ToolSpec(
                name=name,
                description=" ".join(description.split()),
                args_model=args_model,
                fn=fn,
                shape=shape,
                label=label or (lambda _args: name.replace("_", " ")),
            )
            return fn

        return register

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> ToolSpec:
        return self._tools[name]

    def label(self, name: str, args: dict[str, Any]) -> str:
        """The plain label a stored call is shown with, rebuilt from its audited arguments."""
        spec = self._tools.get(name)
        if spec is None:
            return name
        try:
            return spec.label(spec.args_model.model_validate(args))
        except ValidationError:
            return name

    def definitions(self) -> list[ToolDefinition]:
        """Every tool, sorted by name, with a strict schema.

        Sorted and deterministic because the tool list is the start of the cached prompt
        prefix: any byte that moves between requests invalidates everything after it.
        """
        return [
            ToolDefinition(
                name=spec.name,
                description=spec.description,
                input_schema=strict_schema(spec.args_model),
            )
            for spec in (self._tools[name] for name in self.names())
        ]

    def run(self, name: str, raw_args: Any, ctx: ToolContext) -> ToolOutcome:
        """Validate, check the budget, execute read-only, render, audit. Never raises."""
        started = time.perf_counter()
        call_id = ctx.call_ids.next()
        spec = self._tools.get(name)

        def finish(
            status: LookupStatus,
            content: str,
            *,
            args: ToolArgs | None = None,
            rendered: render_module.Rendered | None = None,
            result: ToolResult | None = None,
            rows: int = 0,
            error: str | None = None,
        ) -> ToolOutcome:
            dumped = args.model_dump(mode="json") if args is not None else {}
            outcome = ToolOutcome(
                call_id=call_id,
                tool=name,
                label=spec.label(args) if spec is not None and args is not None else name,
                status=status,
                content=content,
                figures=rendered.figures if rendered else {},
                row_count=rows,
                latency_ms=round((time.perf_counter() - started) * 1000),
                withheld_count=rendered.withheld if rendered else 0,
                arguments=summarize(dumped),
                args=dumped,
                as_of=result.as_of if result else None,
                view=result.view if result else None,
                stale=bool(result.stale) if result else False,
                error=error,
            )
            ctx.audit.record(outcome)
            return outcome

        if spec is None:
            known = ", ".join(self.names())
            return finish(LookupStatus.INVALID_ARGS, f"No tool named {name!r}. Tools: {known}.")

        if not ctx.budget.take_call():
            return finish(
                LookupStatus.BUDGET_EXHAUSTED,
                "This turn has used all its lookups. Answer with what you have, and say what "
                "you could not check.",
            )

        try:
            args = spec.args_model.model_validate(raw_args)
        except ValidationError as exc:
            return finish(LookupStatus.INVALID_ARGS, _explain(exc))

        try:
            with ctx.sessions() as session:
                result = spec.fn(args, session, ctx)
        except (ToolInputError, PeriodError) as exc:
            return finish(
                LookupStatus.INVALID_ARGS, f"{exc} Fix the arguments and call again.", args=args
            )
        except Exception as exc:
            error = type(exc.orig).__name__ if isinstance(exc, DBAPIError) else type(exc).__name__
            # The tool, the call and the exception class. Never arguments or a message,
            # either of which can hold a figure.
            logger.warning("advisor_tool_failed", tool=name, call_id=call_id, error=error)
            return finish(
                LookupStatus.ERROR,
                "The lookup failed. Answer without it and say so.",
                args=args,
                error=error,
            )

        rendered = render_module.render(name, call_id, result, tool_names=self.names())
        rows = result.row_count()
        if not ctx.budget.take(rows, len(rendered.text.encode())):
            return finish(
                LookupStatus.BUDGET_EXHAUSTED,
                "That result would exceed this turn's row or size budget. Narrow the "
                "question — a shorter period, a category, fewer rows — or answer with what "
                "you have.",
                args=args,
            )
        return finish(
            LookupStatus.OK, rendered.text, args=args, rendered=rendered, result=result, rows=rows
        )


def summarize(args: dict[str, Any]) -> str:
    """A readable, bounded summary of validated arguments for the "show lookups" list."""
    parts = [f"{key}={value}" for key, value in args.items() if value is not None]
    summary = ", ".join(parts)
    return summary if len(summary) <= 200 else summary[:199] + "…"


def _explain(exc: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(p) for p in error['loc']) or 'arguments'}: {error['msg']}"
        for error in exc.errors()[:5]
    )
    return f"Invalid arguments — {problems}. Fix them and call again."


# ── schemas ───────────────────────────────────────────────────────────────────

#: Keywords strict tool schemas do not accept. Removed from what is sent and stated in
#: the description instead; Pydantic still enforces every one of them here.
_UNSUPPORTED = {
    "minLength": "at least {} characters",
    "maxLength": "at most {} characters",
    "minimum": "at least {}",
    "maximum": "at most {}",
    "exclusiveMinimum": "more than {}",
    "exclusiveMaximum": "less than {}",
    "pattern": "matching {}",
    "minItems": "at least {} items",
    "maxItems": "at most {} items",
}


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            merged = {**_inline(target, defs), **{k: v for k, v in node.items() if k != "$ref"}}
            return merged
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    return node


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {k: v for k, v in node.items() if k not in {"title", "default"}}
    notes = [
        template.format(node.pop(key)) for key, template in _UNSUPPORTED.items() if key in node
    ]
    for key in ("properties", "items", "anyOf", "allOf"):
        if key in node:
            if key == "properties":
                node[key] = {name: _strictify(prop) for name, prop in node[key].items()}
            else:
                node[key] = _strictify(node[key])
    if node.get("type") == "object" or "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node.get("properties", {}))
    if notes:
        description = node.get("description", "")
        node["description"] = f"{description} ({'; '.join(notes)})".strip()
    return node


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A provider-ready schema: references inlined, every property required (optional ones
    nullable), no extra properties, unsupported constraints moved into descriptions."""
    raw = copy.deepcopy(model.model_json_schema())
    defs = raw.pop("$defs", {})
    schema: dict[str, Any] = _strictify(_inline(raw, defs))
    return schema


def lint_args_model(model: type[BaseModel], name: str = "") -> list[str]:
    """Why an argument model is not safe to hand a model, or `[]` when it is.

    Every string must be an enum, a date, or patterned and bounded; only `merchant_query`
    may be free text, and its pattern must not admit a URL. Every integer is bounded;
    every array is bounded. Checked on the Pydantic schema, before `strict_schema` moves
    the constraints into descriptions.
    """
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    problems: list[str] = []

    def check(prop: str, spec: dict[str, Any]) -> None:
        spec = _inline(spec, defs)
        variants = [v for v in spec.get("anyOf", [spec]) if v.get("type") != "null"]
        for variant in variants:
            kind = variant.get("type")
            if "enum" in variant or "const" in variant:
                continue
            if kind == "string":
                if variant.get("format") in {"date", "date-time"}:
                    continue
                pattern, max_length = variant.get("pattern"), variant.get("maxLength")
                if prop not in FREE_TEXT_ARGUMENTS:
                    problems.append(f"{name}.{prop}: free text is only allowed for merchant_query")
                elif pattern is None or max_length is None:
                    problems.append(f"{name}.{prop}: free text needs a pattern and maxLength")
                elif re.fullmatch(pattern, "http://x") or re.fullmatch(pattern, "a/b"):
                    problems.append(f"{name}.{prop}: the pattern admits a URL")
            elif kind == "integer":
                has_min = "minimum" in variant or "exclusiveMinimum" in variant
                has_max = "maximum" in variant or "exclusiveMaximum" in variant
                if not (has_min and has_max):
                    problems.append(f"{name}.{prop}: integers must be bounded both ways")
            elif kind == "array":
                if "maxItems" not in variant:
                    problems.append(f"{name}.{prop}: arrays must have maxItems")
                check(prop, variant.get("items", {}))
            elif kind == "object":
                for child, child_spec in variant.get("properties", {}).items():
                    check(f"{prop}.{child}", child_spec)
            elif kind == "boolean":
                continue
            else:
                problems.append(f"{name}.{prop}: unsupported type {kind!r}")

    for prop, spec in raw.get("properties", {}).items():
        check(prop, spec)
    return problems


def lint_tool(spec: ToolSpec) -> list[str]:
    """The conventions every tool keeps: a namespaced name, a real description, safe args."""
    problems = lint_args_model(spec.args_model, spec.name)
    if (
        not re.fullmatch(r"[a-z]+(_[a-z]+)+", spec.name)
        or spec.name.split("_")[0] not in NAMESPACES
    ):
        problems.append(f"{spec.name}: names are <area>_<what>, from {sorted(NAMESPACES)}")
    if spec.description.count(". ") < 1:
        problems.append(
            f"{spec.name}: describe it in at least two sentences, as for a new teammate"
        )
    return problems


#: The shared registry. Tool modules register into it when imported; `load_all` imports them.
REGISTRY = Registry()

#: Every module that registers tools. Each ticket that adds tools adds its module here.
TOOL_MODULES: tuple[str, ...] = (
    "app.advisor.tools.balances",
    "app.advisor.tools.spending",
    "app.advisor.tools.cards",
    "app.advisor.tools.analysis",
    "app.advisor.tools.meta",
)


def load_all() -> Registry:
    """Import every tool module, so the shared registry is complete, and return it."""
    import importlib

    for module in TOOL_MODULES:
        importlib.import_module(module)
    return REGISTRY
