"""Card tools: the wallet, the credits about to lapse, and what has been used.

All three read through `services/cards.py`, the implementation the Cards screen uses, so
the chat and the screen cannot disagree about a credit. **None of this is net worth**: an
unused credit is not money you have, and nothing here takes a view, because perks are not
ownership-adjusted.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.tools import (
    REGISTRY,
    Id,
    NoArgs,
    ToolArgs,
    ToolContext,
    ToolInputError,
    ToolResult,
)
from app.models.account import Account
from app.models.card_perk import CardPerk
from app.models.enums import AccountSubtype, PerkCadence
from app.schemas.common import to_cents
from app.services import cards as card_service

#: The most redemptions one history call returns, newest first.
MAX_REDEMPTIONS = 50
#: The longest history window one call may ask for.
MAX_HISTORY_DAYS = 1096


class CurrentPeriod(BaseModel):
    start: dt.date
    end: dt.date = Field(description="The first day of the next period.")
    days_remaining: int = Field(description="0 on the last day of the period.")
    used: bool
    used_amount_cents: int | None = Field(description="A partial use; none means full value.")
    urgent: bool


class PerkRow(BaseModel):
    perk_id: int
    name_text: str
    value_cents: int = Field(description="Face value per period.")
    cadence: PerkCadence
    active: bool
    current_period: CurrentPeriod | None = Field(description="None until the first period starts.")


def _current(view: card_service.PerkView) -> CurrentPeriod | None:
    c = view.current
    if c is None:
        return None
    return CurrentPeriod(
        start=c.start,
        end=c.end,
        days_remaining=c.days_remaining,
        used=c.is_used,
        used_amount_cents=to_cents(c.used_amount) if c.used_amount is not None else None,
        urgent=c.is_urgent,
    )


# ── cards_list ────────────────────────────────────────────────────────────────


class CardRow(BaseModel):
    account_id: int
    name_text: str
    closed: bool
    annual_fee_cents: int | None
    fee_renews_on: dt.date | None
    unused_now_cents: int = Field(description="Face value of active perks unused this period.")
    realised_this_year_cents: int
    active_perk_count: int
    perks: list[PerkRow]


class CardsListResult(ToolResult):
    cards: list[CardRow]


@REGISTRY.tool(
    "cards_list",
    description=(
        "Every credit card with its annual fee, its perks, and each perk's current period: "
        "when it resets, how many days are left, and whether it has been used. Use it for "
        "'what credits do I have' or 'have I used the travel credit this year'. For only the "
        "credits about to lapse use cards_upcoming_perks; for whether a card is worth its fee "
        "use cards_value."
    ),
    label=lambda args: "Cards and their perks",
)
def cards_list(args: NoArgs, session: Session, ctx: ToolContext) -> CardsListResult:
    return CardsListResult(
        as_of=ctx.today,
        cards=[
            CardRow(
                account_id=card.account.id,
                name_text=card.account.name,
                closed=card.account.closed_at is not None,
                annual_fee_cents=(
                    to_cents(card.account.annual_fee)
                    if card.account.annual_fee is not None
                    else None
                ),
                fee_renews_on=card.account.fee_renews_on,
                unused_now_cents=to_cents(card.unused),
                realised_this_year_cents=to_cents(card.realised_this_year),
                active_perk_count=card.active_perk_count,
                perks=[
                    PerkRow(
                        perk_id=view.perk.id,
                        name_text=view.perk.name,
                        value_cents=to_cents(view.perk.value),
                        cadence=view.perk.cadence,
                        active=view.perk.is_active,
                        current_period=_current(view),
                    )
                    for view in card.perks
                ],
            )
            for card in card_service.list_cards(session, ctx.today)
        ],
    )


# ── cards_upcoming_perks ──────────────────────────────────────────────────────


class UpcomingArgs(ToolArgs):
    within_days: int = Field(
        default=30,
        ge=0,
        le=366,
        description="Perks whose current period ends within this many days.",
    )


class UpcomingRow(BaseModel):
    perk_id: int
    perk_name_text: str
    card_account_id: int
    card_name_text: str
    value_cents: int
    period_ends: dt.date = Field(description="The last day to use it.")
    days_remaining: int
    urgent: bool


class UpcomingResult(ToolResult):
    within_days: int
    total_cents: int
    urgent_cents: int
    perks: list[UpcomingRow]


@REGISTRY.tool(
    "cards_upcoming_perks",
    description=(
        "Unused perks whose current period ends soon, soonest first — the credits about to be "
        "lost. Urgency is fixed per cadence: the last 7 days of a monthly credit, 14 of a "
        "quarterly one, 21 of a half-yearly one, 30 of an annual one. Closed cards and retired "
        "perks are left out. For the whole wallet use cards_list."
    ),
    label=lambda args: f"Perks ending within {args.within_days} days",
)
def cards_upcoming_perks(args: UpcomingArgs, session: Session, ctx: ToolContext) -> UpcomingResult:
    result = card_service.upcoming(session, args.within_days, ctx.today)
    rows = []
    for item in result.items:
        current = item.view.current
        assert current is not None  # upcoming only returns perks in a current period
        rows.append(
            UpcomingRow(
                perk_id=item.view.perk.id,
                perk_name_text=item.view.perk.name,
                card_account_id=item.account.id,
                card_name_text=item.account.name,
                value_cents=to_cents(item.view.perk.value),
                period_ends=current.end - dt.timedelta(days=1),
                days_remaining=current.days_remaining,
                urgent=current.is_urgent,
            )
        )
    return UpcomingResult(
        as_of=ctx.today,
        within_days=args.within_days,
        total_cents=to_cents(result.total),
        urgent_cents=to_cents(result.urgent),
        perks=rows,
    )


# ── cards_perk_history ────────────────────────────────────────────────────────


class PerkHistoryArgs(ToolArgs):
    account_id: Id | None = Field(default=None, description="One card, from cards_list.")
    perk_id: Id | None = Field(default=None, description="One perk, from cards_list.")
    start: dt.date | None = Field(
        default=None, description="Periods starting on or after this. Defaults to 1 January."
    )
    end: dt.date | None = Field(default=None, description="Defaults to today.")


class RedemptionRow(BaseModel):
    perk_id: int
    perk_name_text: str
    card_name_text: str
    period_start: dt.date
    period_ends: dt.date
    realised_cents: int
    full_value: bool = Field(description="Marked used in full rather than a partial amount.")
    note_text: str | None


class PerkHistoryResult(ToolResult):
    start: dt.date
    end: dt.date
    realised_cents: int = Field(description="Value used across every redemption in the window.")
    missed_periods: int = Field(description="Periods that ended in the window with nothing used.")
    redemptions: list[RedemptionRow]
    showing_latest_only: bool

    def row_count(self) -> int:
        return len(self.redemptions)


@REGISTRY.tool(
    "cards_perk_history",
    description=(
        "What was used, perk by perk, over a window of up to three years: each redemption with "
        "the value it realised, the total, and how many periods ended unused. Filter to one card "
        "or one perk. Value realised is the amount recorded, or face value for a one-tap mark — "
        "never what was merely available. For value against the annual fee use cards_value."
    ),
    shape="rows",
    label=lambda args: "Perk history",
)
def cards_perk_history(
    args: PerkHistoryArgs, session: Session, ctx: ToolContext
) -> PerkHistoryResult:
    end = args.end or ctx.today
    start = args.start or dt.date(end.year, 1, 1)
    if end > ctx.today:
        raise ToolInputError(f"end is after today ({ctx.today.isoformat()}).")
    if start > end:
        raise ToolInputError("start must be on or before end.")
    if (end - start).days > MAX_HISTORY_DAYS:
        raise ToolInputError("A perk history covers at most three years.")
    if args.perk_id is not None and session.get(CardPerk, args.perk_id) is None:
        raise ToolInputError(f"No perk with id {args.perk_id}. Use cards_list for ids.")
    if args.account_id is not None:
        account = session.get(Account, args.account_id)
        if account is None or account.subtype is not AccountSubtype.CREDIT_CARD:
            raise ToolInputError(f"No card with id {args.account_id}. Use cards_list for ids.")

    history = card_service.history(
        session,
        perk_id=args.perk_id,
        account_id=args.account_id,
        from_date=start,
        to_date=end,
        today=ctx.today,
    )
    entries = history.entries[:MAX_REDEMPTIONS]
    return PerkHistoryResult(
        as_of=ctx.today,
        start=start,
        end=end,
        realised_cents=to_cents(history.realised),
        missed_periods=history.missed_periods,
        redemptions=[
            RedemptionRow(
                perk_id=e.perk.id,
                perk_name_text=e.perk.name,
                card_name_text=e.account.name,
                period_start=e.redemption.period_start,
                period_ends=e.period_end - dt.timedelta(days=1),
                realised_cents=to_cents(e.realised),
                full_value=e.redemption.amount is None,
                note_text=e.redemption.note,
            )
            for e in entries
        ],
        showing_latest_only=len(history.entries) > MAX_REDEMPTIONS,
    )
