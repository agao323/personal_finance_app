"""The Insights and advisor contract (ticket 081).

Declared whole, before any of it is implemented, for the reason ticket 012 declared the v1
surface: the tools, the loop and the web lane build against one frozen file and cannot
drift. See docs/ADVISOR.md.

Three conventions carry over from the rest of the contract and one is new:

- **Money is `*_cents`, percentages are `*_bps`, never a float.** Ratios that are neither
  are fixed-point integers with the scale in the name (`value_months_tenths`).
- **Enums ship complete.** `FindingKind` and `LimitationKind` list every kind planned for
  Waves 9-12, as `models/enums.py` does, so a later wave adds a finding without a
  contract change.
- **Nothing here is a URL.** An action points at a `Screen`, and the web maps screens to
  routes in one function. A model-authored URL is the thing the renderer must never draw.
- **New: a figure carries its proof.** `FigureCheck` records whether a number in an answer
  was written by the server from a tool result (`verified`), typed by the model and found
  in one (`matched`), or neither (`unverified`) — the Proof-Carrying Numbers shape in
  docs/ADVISOR.md#grounding.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Annotated, Literal

from pydantic import Field, RootModel

from app.schemas.common import Cents, Schema, ViewScope

# ── Insights ──────────────────────────────────────────────────────────────────


class FindingKind(enum.StrEnum):
    """Every finding the engine can produce, across Waves 9-12.

    The wave that implements each is in docs/ADVISOR.md#findings. Declared now so the
    Insights panel can be written once, against the whole set.
    """

    # Wave 9
    PERK_EXPIRING = "perk_expiring"
    POSSIBLE_UNMARKED_TRANSFER = "possible_unmarked_transfer"
    STALE_BALANCE = "stale_balance"
    RUNWAY_LOW = "runway_low"
    SPEND_SPIKE = "spend_spike"
    RECURRING_PRICE_INCREASE = "recurring_price_increase"
    UNCATEGORISED_SPEND = "uncategorised_spend"
    TRANSACTIONS_NOT_IMPORTED = "transactions_not_imported"
    CARD_FEE_UNCOVERED = "card_fee_uncovered"
    NET_WORTH_DROP = "net_worth_drop"
    SPEND_INCREASE = "spend_increase"
    RECURRING_SUMMARY = "recurring_summary"
    # Wave 11
    GOAL_OFF_TRACK = "goal_off_track"
    SPENDING_LIMIT_EXCEEDED = "spending_limit_exceeded"
    EMERGENCY_FUND_BELOW_TARGET = "emergency_fund_below_target"
    # Wave 12
    HIGH_INTEREST_DEBT = "high_interest_debt"
    CREDIT_UTILISATION_HIGH = "credit_utilisation_high"
    ALLOCATION_DRIFT = "allocation_drift"
    CASH_DRAG = "cash_drag"


class Severity(enum.StrEnum):
    """Most urgent first. The panel keeps the server's order; it never re-sorts."""

    URGENT = "urgent"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"


class EvidenceUnit(enum.StrEnum):
    """Which `value_*` field of an `Evidence` is populated. Exactly one ever is."""

    CENTS = "cents"
    BPS = "bps"
    COUNT = "count"
    DAYS = "days"
    MONTHS_TENTHS = "months_tenths"
    DATE = "date"


class Screen(enum.StrEnum):
    """An in-app destination. The web maps each to a route in `lib/screens.ts`."""

    DASHBOARD = "dashboard"
    SPENDING = "spending"
    TRANSACTIONS = "transactions"
    ACCOUNTS = "accounts"
    ACCOUNT = "account"
    CARDS = "cards"
    IMPORT = "import"
    RULES = "rules"
    GOALS = "goals"
    PLANNING = "planning"
    ADVISOR = "advisor"


class ActionKind(enum.StrEnum):
    """What the action asks the owner to do. Always something done on a screen, by hand."""

    OPEN = "open"
    UPDATE_BALANCE = "update_balance"
    IMPORT_TRANSACTIONS = "import_transactions"
    ADD_RULE = "add_rule"
    MARK_TRANSFER = "mark_transfer"
    USE_PERK = "use_perk"
    REVIEW = "review"


class Evidence(Schema):
    """One figure a finding rests on, and where it came from."""

    label: str
    unit: EvidenceUnit
    value_cents: Cents | None = None
    value_bps: int | None = Field(
        default=None, description="Basis points; may be negative or exceed 10000 for a change."
    )
    value_count: int | None = None
    value_months_tenths: int | None = Field(
        default=None, description="Months x 10: 234 means 23.4 months."
    )
    value_date: dt.date | None = None
    as_of: dt.date
    stale: bool = Field(description="The figure rests on a balance carried forward past 90 days.")
    source: str = Field(description="The analysis that computed it, e.g. `spend_trends.monthly`.")


class FindingAction(Schema):
    """Where to go to act on a finding. Never a URL."""

    kind: ActionKind
    screen: Screen
    account_id: int | None = None
    category_id: int | None = None
    perk_id: int | None = None
    transaction_ids: list[int]


class Finding(Schema):
    """A structured observation from the findings engine. No model is involved.

    `title` and `detail` are server-rendered from templates and evidence, and can contain
    imported text such as a merchant name. They are plain text: render them as text,
    never as markdown or HTML.
    """

    id: str = Field(description="Stable across runs: kind + subject ids + period.")
    kind: FindingKind
    severity: Severity
    title: str
    detail: str
    as_of: dt.date
    stale: bool
    impact_cents: Cents | None = Field(
        default=None, description="Annualised money at stake, used for ranking."
    )
    evidence: list[Evidence]
    action: FindingAction | None = None


class InsightsRead(Schema):
    """Findings for a scope, ranked: severity, then impact, then kind."""

    as_of: dt.date
    view: ViewScope
    findings: list[Finding]


# ── The advisor ───────────────────────────────────────────────────────────────


class AdvisorProvider(enum.StrEnum):
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    SCRIPTED = "scripted"


class AdvisorErrorCode(enum.StrEnum):
    """Why a turn did not produce an answer, or was refused before it started.

    Each is a distinct message in the UI. "Something went wrong" is not one of them.
    """

    DISABLED = "disabled"
    DEMO = "demo"
    NOT_CONFIGURED = "not_configured"
    MONTHLY_CAP = "monthly_cap"
    CONVERSATION_CAP = "conversation_cap"
    TURN_CAP = "turn_cap"
    TURN_IN_PROGRESS = "turn_in_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    CANCELLED = "cancelled"
    MODEL_ERROR = "model_error"


class AdvisorStatus(Schema):
    """Whether a question can be asked right now, and what this month has cost."""

    enabled: bool
    reason: AdvisorErrorCode | None = Field(
        default=None, description="Why not, when `enabled` is false."
    )
    provider: AdvisorProvider
    model: str | None = None
    month_spent_cents: Cents
    month_cap_cents: Cents
    resets_on: dt.date = Field(description="The first day of next month, UTC.")


class LimitationKind(enum.StrEnum):
    """Data a question needed that the app does not have. Recorded by `note_limitation`.

    Counted in the audit log, these rank what to build next — see docs/ADVISOR.md.
    """

    HOLDINGS = "holdings"
    TAX_TREATMENT = "tax_treatment"
    LIABILITY_TERMS = "liability_terms"
    GOALS = "goals"
    CREDIT_LIMITS = "credit_limits"
    REWARD_MULTIPLIERS = "reward_multipliers"
    CREDIT_SCORE = "credit_score"
    INCOME_HISTORY = "income_history"
    BALANCE_HISTORY = "balance_history"
    TRANSACTION_COVERAGE = "transaction_coverage"
    PROJECTIONS = "projections"
    MARKET_DATA = "market_data"
    TAX_OR_LEGAL_ADVICE = "tax_or_legal_advice"
    OTHER = "other"


class TurnStatus(enum.StrEnum):
    STREAMING = "streaming"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REFUSED = "refused"


class Grounding(enum.StrEnum):
    """`verified`: every figure checked. `flagged`: at least one was not. `none`: no figures."""

    VERIFIED = "verified"
    FLAGGED = "flagged"
    NONE = "none"


class FigureStatus(enum.StrEnum):
    VERIFIED = "verified"
    MATCHED = "matched"
    UNVERIFIED = "unverified"


class FigureSource(Schema):
    call_id: str = Field(description="The tool call the figure came from, e.g. `c2`.")
    path: str = Field(description="Where in that result, e.g. `buckets.3.change`.")


class FigureCheck(Schema):
    """One figure in an answer's text: where it is, and what proves it."""

    start: int = Field(ge=0, description="Character offset into `Answer.text`.")
    end: int = Field(ge=0)
    status: FigureStatus
    source: FigureSource | None = None
    reason: str | None = Field(default=None, description="Why a figure is unverified.")


class Citation(Schema):
    """A source line under an answer. Assembled by the system, never by the model."""

    call_id: str
    tool: str
    label: str
    as_of: dt.date | None = None
    view: ViewScope | None = None
    stale: bool


class LookupStatus(enum.StrEnum):
    OK = "ok"
    INVALID_ARGS = "invalid_args"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ERROR = "error"


class Lookup(Schema):
    """One tool call, as the "show lookups" control lists it."""

    call_id: str
    tool: str
    label: str
    arguments: str = Field(description="A readable summary of the validated arguments.")
    status: LookupStatus
    row_count: int
    latency_ms: int
    as_of: dt.date | None = None


class PolicyCheck(enum.StrEnum):
    TICKER_OR_ISSUER = "ticker_or_issuer"
    CLAIMED_ACTION = "claimed_action"
    TAX_FIGURE = "tax_figure"
    SCOPE_LABEL = "scope_label"


class PolicyNote(Schema):
    """A policy check an answer still failed after its one retry. Shown on the answer."""

    check: PolicyCheck
    message: str


class Answer(Schema):
    """The checked answer: text, the proof for each figure, and its sources.

    `text` is a restricted markdown subset with every link, image and HTML tag already
    removed. Render it with the app's own renderer, never a general markdown library.
    """

    text: str
    figures: list[FigureCheck]
    citations: list[Citation]
    limitations: list[LimitationKind]
    policy_notes: list[PolicyNote]
    truncated: bool


class Feedback(enum.StrEnum):
    GOOD = "good"
    FLAGGED = "flagged"


class TurnFeedback(Schema):
    """The owner's verdict on one answer. Stays in the app; feeds the monthly review."""

    verdict: Feedback
    note: str | None = Field(default=None, max_length=500)


class TurnRead(Schema):
    id: uuid.UUID
    seq: int
    question: str
    status: TurnStatus
    grounding: Grounding
    answer: Answer | None = None
    lookups: list[Lookup]
    error: AdvisorErrorCode | None = None
    feedback: Feedback | None = None
    feedback_note: str | None = None
    started_at: dt.datetime
    finished_at: dt.datetime | None = None


class ConversationCreate(Schema):
    view: ViewScope = Field(description="Mine or Household. Spend is never split either way.")


class ConversationSummary(Schema):
    """A conversation in the list. Each person sees only their own."""

    id: uuid.UUID
    view: ViewScope
    title: str
    created_at: dt.datetime
    last_turn_at: dt.datetime | None = None
    expires_at: dt.datetime = Field(description="Deleted 30 days after the last turn.")
    turn_count: int


class ConversationDetail(ConversationSummary):
    turns: list[TurnRead]


class TurnCreate(Schema):
    question: str = Field(min_length=1, max_length=2000)


# ── Streamed events ───────────────────────────────────────────────────────────
#
# A turn answers as server-sent events, one JSON object per `data:` line, discriminated
# by `type`. The order is fixed: `turn_started` first, then any of `tool_call`,
# `text_delta`, `regenerating` and `heartbeat`, then `answer` or `error`, then
# `turn_complete` — see docs/ADVISOR.md#one-turn.


class TurnStartedEvent(Schema):
    type: Literal["turn_started"]
    turn_id: uuid.UUID
    conversation_id: uuid.UUID


class ToolCallEvent(Schema):
    type: Literal["tool_call"]
    lookup: Lookup


class TextDeltaEvent(Schema):
    """Streamed text. References are already resolved; statuses arrive with `answer`."""

    type: Literal["text_delta"]
    text: str


class AnswerEvent(Schema):
    type: Literal["answer"]
    answer: Answer


class RegeneratingEvent(Schema):
    """The streamed text failed a check and is being written again. Discard it."""

    type: Literal["regenerating"]
    reason: str


class ErrorEvent(Schema):
    type: Literal["error"]
    code: AdvisorErrorCode
    message: str
    resets_on: dt.date | None = None


class HeartbeatEvent(Schema):
    type: Literal["heartbeat"]


class TurnCompleteEvent(Schema):
    type: Literal["turn_complete"]
    turn_id: uuid.UUID
    grounding: Grounding
    cost_cents: Cents = Field(description="What this turn cost, rounded once to cents.")
    month_spent_cents: Cents


class AdvisorEvent(
    RootModel[
        Annotated[
            TurnStartedEvent
            | ToolCallEvent
            | TextDeltaEvent
            | AnswerEvent
            | RegeneratingEvent
            | ErrorEvent
            | HeartbeatEvent
            | TurnCompleteEvent,
            Field(discriminator="type"),
        ]
    ]
):
    """One event on a turn's stream. Declared as a model so the union reaches the types."""
