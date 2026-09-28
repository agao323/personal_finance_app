"""The findings engine: analyses turned into ranked, structured observations.

**This is what makes recommendations testable without a model** (ADR 0011). The engine decides
what is worth saying, how urgent it is, on what evidence, and where in the app to act. The
Insights panel shows its output directly; the advisor, when on, explains and prioritises
findings for the question asked. Neither creates one.

Findings are built straight into the contract's `Finding` shape — money as cents, ratios as
basis points — because they are a read model for display and have no other consumer. Titles
are server-rendered from templates and evidence; they can contain imported text such as a
merchant name, and are plain text wherever they are shown.

**Stale evidence demotes a finding.** A recommendation resting on a four-month-old balance is
what "no push to act on stale data" exists to stop, so it is capped at `notice` and its action
becomes "update this balance" — except `stale_balance`, which is *about* the staleness.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind, GoalKind, GoalStatus
from app.models.goal import Goal
from app.models.transaction import Category
from app.schemas.advisor import (
    ActionKind,
    Evidence,
    EvidenceUnit,
    Finding,
    FindingAction,
    FindingKind,
    Screen,
    Severity,
)
from app.schemas.common import ViewScope, to_cents
from app.services import cards as card_service
from app.services import net_worth as net_worth_service
from app.services import runway as runway_service
from app.services.analysis import cards_value, data_quality, recurring, spend_trends
from app.services.analysis import goals as goal_analysis
from app.services.analysis.numbers import change_bps, quantize_money, tenths
from app.services.analysis.periods import PeriodPreset, resolve
from app.services.perks import add_months

# ── thresholds: one table, fixed, revisited after a month of real use ─────────

#: A credit this many days or fewer from lapsing, and urgent by its cadence's rule.
PERK_WINDOW_DAYS = 30
#: Runway below this many months, on the 6-month window, until goals set a target.
RUNWAY_LOW_MONTHS = Decimal("3")
RUNWAY_WINDOW = 6
#: Uncategorised spend above this share of last month's, or this many rows.
UNCATEGORISED_SHARE_BPS = 500
UNCATEGORISED_ROWS = 10
#: An account that imports transactions but has none this recent.
QUIET_IMPORT_DAYS = 35
#: A fee renewing this soon, with less realised than it costs.
FEE_RENEWAL_DAYS = 60
#: Net worth down more than this share of its size, month over month.
NET_WORTH_DROP_BPS = 500
#: Quarter-to-date spending up more than this share and this much, like-for-like.
SPEND_INCREASE_BPS = 2000
SPEND_INCREASE_MIN = Decimal("100.00")
#: The most transfer pairs, stale accounts or spikes reported at once.
MAX_PER_KIND = 5

_SEVERITY_ORDER = {Severity.URGENT: 0, Severity.WARNING: 1, Severity.NOTICE: 2, Severity.INFO: 3}
_KIND_ORDER = {kind: index for index, kind in enumerate(FindingKind)}


def _money(value: Decimal) -> str:
    """For titles only. Figures a model quotes come from evidence, never from a title."""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _evidence(
    label: str,
    unit: EvidenceUnit,
    value: Decimal | int | dt.date,
    as_of: dt.date,
    source: str,
    stale: bool = False,
) -> Evidence:
    fields: dict[str, object] = {}
    if unit is EvidenceUnit.CENTS:
        assert isinstance(value, Decimal)
        fields["value_cents"] = to_cents(quantize_money(value))
    elif unit is EvidenceUnit.DATE:
        fields["value_date"] = value
    elif unit is EvidenceUnit.BPS:
        fields["value_bps"] = value
    elif unit is EvidenceUnit.MONTHS_TENTHS:
        fields["value_months_tenths"] = value
    else:
        fields["value_count"] = value
    return Evidence(label=label, unit=unit, as_of=as_of, stale=stale, source=source, **fields)


def _action(
    kind: ActionKind,
    screen: Screen,
    *,
    account_id: int | None = None,
    category_id: int | None = None,
    perk_id: int | None = None,
    transaction_ids: list[int] | None = None,
) -> FindingAction:
    return FindingAction(
        kind=kind,
        screen=screen,
        account_id=account_id,
        category_id=category_id,
        perk_id=perk_id,
        transaction_ids=transaction_ids or [],
    )


def _finding(
    kind: FindingKind,
    subject: str,
    severity: Severity,
    title: str,
    detail: str,
    today: dt.date,
    evidence: list[Evidence],
    action: FindingAction | None,
    impact: Decimal | None = None,
) -> Finding:
    stale = any(e.stale for e in evidence)
    if stale and kind is not FindingKind.STALE_BALANCE:
        if _SEVERITY_ORDER[severity] < _SEVERITY_ORDER[Severity.NOTICE]:
            severity = Severity.NOTICE
        action = _action(ActionKind.UPDATE_BALANCE, Screen.ACCOUNTS)
        detail = f"{detail} It rests on a balance more than 90 days old — update it first."
    return Finding(
        id=f"{kind.value}:{subject}",
        kind=kind,
        severity=severity,
        title=title,
        detail=detail,
        as_of=today,
        stale=stale,
        impact_cents=to_cents(quantize_money(abs(impact))) if impact is not None else None,
        evidence=evidence,
        action=action,
    )


# ── each kind ─────────────────────────────────────────────────────────────────


def _perks_expiring(session: Session, today: dt.date) -> list[Finding]:
    found = []
    for item in card_service.upcoming(session, PERK_WINDOW_DAYS, today).items:
        current = item.view.current
        if current is None or not current.is_urgent:
            continue
        perk = item.view.perk
        days = current.days_remaining
        when = "today" if days == 0 else f"in {days + 1} days"
        found.append(
            _finding(
                FindingKind.PERK_EXPIRING,
                f"perk{perk.id}:{current.start.isoformat()}",
                Severity.URGENT,
                f"{perk.name} on {item.account.name}: {_money(perk.value)} lapses {when}",
                "This period's credit is unused and resets at the end of the period.",
                today,
                [
                    _evidence("Credit", EvidenceUnit.CENTS, perk.value, today, "cards.upcoming"),
                    _evidence("Days left", EvidenceUnit.DAYS, days, today, "cards.upcoming"),
                    _evidence(
                        "Last day",
                        EvidenceUnit.DATE,
                        current.end - dt.timedelta(days=1),
                        today,
                        "cards.upcoming",
                    ),
                ],
                _action(
                    ActionKind.USE_PERK, Screen.CARDS, account_id=item.account.id, perk_id=perk.id
                ),
                impact=perk.value,
            )
        )
    return found


def _health_findings(session: Session, today: dt.date) -> list[Finding]:
    health = data_quality.health(session, today)
    found: list[Finding] = []

    for pair in health.pairs[:MAX_PER_KIND]:
        found.append(
            _finding(
                FindingKind.POSSIBLE_UNMARKED_TRANSFER,
                f"tx{pair.outflow.id}-tx{pair.inflow.id}",
                Severity.WARNING,
                f"A {_money(pair.inflow.amount)} move may be counted as spending",
                "Two transactions on different accounts cancel out within a few days. If they "
                "are a transfer, marking them keeps them out of spending and runway.",
                today,
                [
                    _evidence(
                        "Amount", EvidenceUnit.CENTS, pair.inflow.amount, today, "data_quality"
                    ),
                    _evidence(
                        "Out", EvidenceUnit.DATE, pair.outflow.posted_at, today, "data_quality"
                    ),
                    _evidence(
                        "In", EvidenceUnit.DATE, pair.inflow.posted_at, today, "data_quality"
                    ),
                ],
                _action(
                    ActionKind.MARK_TRANSFER,
                    Screen.TRANSACTIONS,
                    transaction_ids=[pair.outflow.id, pair.inflow.id],
                ),
                impact=pair.inflow.amount,
            )
        )

    share = health.uncategorised_share_bps
    if health.uncategorised_count >= UNCATEGORISED_ROWS or (
        share is not None and share > UNCATEGORISED_SHARE_BPS
    ):
        month = health.month.strftime("%B")
        found.append(
            _finding(
                FindingKind.UNCATEGORISED_SPEND,
                health.month.strftime("%Y-%m"),
                Severity.NOTICE,
                f"{_money(health.uncategorised_spend)} of {month}'s spending is uncategorised",
                "Spending without a category is counted, but no breakdown can explain it. A rule "
                "fixes it for every future import.",
                today,
                [
                    _evidence(
                        "Uncategorised",
                        EvidenceUnit.CENTS,
                        health.uncategorised_spend,
                        today,
                        "data_quality",
                    ),
                    _evidence(
                        "Transactions",
                        EvidenceUnit.COUNT,
                        health.uncategorised_count,
                        today,
                        "data_quality",
                    ),
                    *(
                        [_evidence("Share", EvidenceUnit.BPS, share, today, "data_quality")]
                        if share is not None
                        else []
                    ),
                ],
                _action(ActionKind.ADD_RULE, Screen.RULES),
            )
        )

    for account in health.accounts:
        last = account.last_transaction
        if last is None:
            continue
        days = (today - last).days
        if days > QUIET_IMPORT_DAYS:
            found.append(
                _finding(
                    FindingKind.TRANSACTIONS_NOT_IMPORTED,
                    f"acct{account.account.id}",
                    Severity.NOTICE,
                    f"No transactions imported for {account.account.name} in {days} days",
                    "Spending for this account stops at the last import, so recent months "
                    "read low.",
                    today,
                    [
                        _evidence(
                            "Last transaction",
                            EvidenceUnit.DATE,
                            last,
                            today,
                            "data_quality",
                        ),
                        _evidence("Days", EvidenceUnit.DAYS, days, today, "data_quality"),
                    ],
                    _action(
                        ActionKind.IMPORT_TRANSACTIONS, Screen.IMPORT, account_id=account.account.id
                    ),
                )
            )
    return found


def _stale_balances(session: Session, today: dt.date, viewer_id: int | None) -> list[Finding]:
    worth = net_worth_service.net_worth(session, today, viewer_id)
    stale = [c for c in worth.contributions if c.is_stale]
    stale.sort(key=lambda c: -c.adjusted_balance)
    found = []
    for c in stale[:MAX_PER_KIND]:
        days = (today - c.balance_as_of).days
        found.append(
            _finding(
                FindingKind.STALE_BALANCE,
                f"acct{c.account_id}",
                Severity.WARNING,
                f"{session.get_one(Account, c.account_id).name}'s balance is {days} days old",
                "Net worth still counts it, carried forward, but every figure built on it is a "
                "guess until it is updated.",
                today,
                [
                    _evidence(
                        "Balance date", EvidenceUnit.DATE, c.balance_as_of, today, "net_worth", True
                    ),
                    _evidence("Days old", EvidenceUnit.DAYS, days, today, "net_worth", True),
                    _evidence(
                        "Counted as",
                        EvidenceUnit.CENTS,
                        c.adjusted_balance,
                        today,
                        "net_worth",
                        True,
                    ),
                ],
                _action(ActionKind.UPDATE_BALANCE, Screen.ACCOUNT, account_id=c.account_id),
                impact=c.adjusted_balance,
            )
        )
    return found


def _runway_low(session: Session, today: dt.date, viewer_id: int | None) -> list[Finding]:
    result = runway_service.runway(session, today=today, viewer_id=viewer_id)
    window = next(w for w in result.windows if w.months == RUNWAY_WINDOW)
    if window.average_monthly_spend <= 0:
        return []
    months = result.liquid_assets / window.average_monthly_spend
    if months >= RUNWAY_LOW_MONTHS:
        return []
    worth = net_worth_service.net_worth(session, today, viewer_id)
    stale = any(c.is_stale and c.kind is AccountKind.LIQUID_ASSET for c in worth.contributions)
    return [
        _finding(
            FindingKind.RUNWAY_LOW,
            today.strftime("%Y-%m"),
            Severity.WARNING,
            f"Liquid assets cover {Decimal(tenths(months)).scaleb(-1)} months of spending",
            "At the last six months' average spending, with no income. Three months is a "
            "default threshold until an emergency-fund goal sets one.",
            today,
            [
                _evidence(
                    "Runway", EvidenceUnit.MONTHS_TENTHS, tenths(months), today, "runway", stale
                ),
                _evidence(
                    "Liquid assets",
                    EvidenceUnit.CENTS,
                    result.liquid_assets,
                    today,
                    "runway",
                    stale,
                ),
                _evidence(
                    "Average monthly spending",
                    EvidenceUnit.CENTS,
                    window.average_monthly_spend,
                    today,
                    "runway",
                ),
                _evidence(
                    "Default threshold",
                    EvidenceUnit.MONTHS_TENTHS,
                    tenths(RUNWAY_LOW_MONTHS),
                    today,
                    "findings",
                ),
            ],
            _action(ActionKind.OPEN, Screen.DASHBOARD),
        )
    ]


def _spend_spikes(session: Session, today: dt.date) -> list[Finding]:
    found = []
    for spike in spend_trends.category_spikes(session, today)[:MAX_PER_KIND]:
        month = spike.month.strftime("%B")
        found.append(
            _finding(
                FindingKind.SPEND_SPIKE,
                f"cat{spike.category_id}:{spike.month.strftime('%Y-%m')}",
                Severity.NOTICE,
                f"{spike.name} was {_money(spike.excess)} above usual in {month}",
                "More than one and a half times the median of the six months before it.",
                today,
                [
                    _evidence(month, EvidenceUnit.CENTS, spike.spend, today, "spend_trends"),
                    _evidence(
                        "Usual month",
                        EvidenceUnit.CENTS,
                        spike.trailing_median,
                        today,
                        "spend_trends",
                    ),
                    _evidence(
                        "Above usual", EvidenceUnit.CENTS, spike.excess, today, "spend_trends"
                    ),
                ],
                _action(ActionKind.OPEN, Screen.SPENDING, category_id=spike.category_id),
                impact=spike.excess,
            )
        )
    return found


def _recurring(session: Session, today: dt.date) -> list[Finding]:
    charges = recurring.find(session, today, 12)
    active = [c for c in charges if c.status == "active"]
    found = []
    for c in active:
        if c.price_increase is None:
            continue
        found.append(
            _finding(
                FindingKind.RECURRING_PRICE_INCREASE,
                c.merchant,
                Severity.NOTICE,
                f"{c.merchant} went up {_money(c.price_increase)} per {c.cadence.name} charge",
                f"Now {_money(c.last_amount)} a charge, about {_money(c.annualised)} a year.",
                today,
                [
                    _evidence("Increase", EvidenceUnit.CENTS, c.price_increase, today, "recurring"),
                    *(
                        [
                            _evidence(
                                "Increase",
                                EvidenceUnit.BPS,
                                c.price_increase_bps,
                                today,
                                "recurring",
                            )
                        ]
                        if c.price_increase_bps is not None
                        else []
                    ),
                    _evidence(
                        "Latest charge", EvidenceUnit.CENTS, c.last_amount, today, "recurring"
                    ),
                    _evidence(
                        "A year at this price", EvidenceUnit.CENTS, c.annualised, today, "recurring"
                    ),
                ],
                _action(ActionKind.REVIEW, Screen.TRANSACTIONS),
                impact=c.price_increase * c.cadence.per_year,
            )
        )
    if active:
        total = recurring.active_annual_total(active)
        found.append(
            _finding(
                FindingKind.RECURRING_SUMMARY,
                today.strftime("%Y-%m"),
                Severity.INFO,
                f"{len(active)} recurring charges, about {_money(total)} a year",
                "Subscriptions and regular services found from the rhythm of past charges.",
                today,
                [
                    _evidence(
                        "Recurring charges", EvidenceUnit.COUNT, len(active), today, "recurring"
                    ),
                    _evidence("A year", EvidenceUnit.CENTS, total, today, "recurring"),
                ],
                _action(ActionKind.OPEN, Screen.ADVISOR),
            )
        )
    return found


def _fees_uncovered(session: Session, today: dt.date) -> list[Finding]:
    found = []
    for card in cards_value.value(session, today.year, today):
        renews = card.account.fee_renews_on
        if card.fee is None or renews is None:
            continue
        days = (renews - today).days
        if not 0 <= days <= FEE_RENEWAL_DAYS or card.realised >= card.fee:
            continue
        found.append(
            _finding(
                FindingKind.CARD_FEE_UNCOVERED,
                f"acct{card.account.id}:{renews.isoformat()}",
                Severity.NOTICE,
                f"{card.account.name}'s {_money(card.fee)} fee renews in {days} days",
                f"Perks used this year are worth {_money(card.realised)} — less than the fee.",
                today,
                [
                    _evidence("Annual fee", EvidenceUnit.CENTS, card.fee, today, "cards_value"),
                    _evidence(
                        "Used this year", EvidenceUnit.CENTS, card.realised, today, "cards_value"
                    ),
                    _evidence("Renews", EvidenceUnit.DATE, renews, today, "cards_value"),
                ],
                _action(ActionKind.REVIEW, Screen.CARDS, account_id=card.account.id),
                impact=card.fee - card.realised,
            )
        )
    return found


def _net_worth_drop(session: Session, today: dt.date, viewer_id: int | None) -> list[Finding]:
    before_date = add_months(today, -1)
    before = net_worth_service.net_worth(session, before_date, viewer_id)
    after = net_worth_service.net_worth(session, today, viewer_id)
    if not before.contributions or before.net_worth == 0:
        return []
    change = after.net_worth - before.net_worth
    bps = change_bps(after.net_worth, before.net_worth)
    if change >= 0 or bps is None or -bps <= NET_WORTH_DROP_BPS:
        return []
    stale = before.stale_count > 0 or after.stale_count > 0
    return [
        _finding(
            FindingKind.NET_WORTH_DROP,
            today.strftime("%Y-%m"),
            Severity.NOTICE,
            f"Net worth is down {_money(-change)} on a month ago",
            "Ask the advisor why, or open the chart: the change is attributed account by account.",
            today,
            [
                _evidence("Change", EvidenceUnit.CENTS, change, today, "net_worth", stale),
                _evidence("Change", EvidenceUnit.BPS, bps, today, "net_worth", stale),
                _evidence("A month ago", EvidenceUnit.DATE, before_date, today, "net_worth"),
            ],
            _action(ActionKind.OPEN, Screen.DASHBOARD),
        )
    ]


def _spend_increase(session: Session, today: dt.date) -> list[Finding]:
    result = spend_trends.compare(
        session,
        resolve(PeriodPreset.THIS_QUARTER, today),
        resolve(PeriodPreset.LAST_QUARTER, today),
    )
    bps = result.total_change_bps
    if bps is None or bps <= SPEND_INCREASE_BPS or result.total_change < SPEND_INCREASE_MIN:
        return []
    return [
        _finding(
            FindingKind.SPEND_INCREASE,
            result.a.start.isoformat(),
            Severity.INFO,
            f"Spending this quarter is up {_money(result.total_change)} on last quarter",
            "Compared over the same number of days, so a quarter still in progress is not "
            "measured against a whole one.",
            today,
            [
                _evidence(
                    "This quarter", EvidenceUnit.CENTS, result.total_a, today, "spend_trends"
                ),
                _evidence(
                    "Last quarter, same days",
                    EvidenceUnit.CENTS,
                    result.total_b,
                    today,
                    "spend_trends",
                ),
                _evidence("Change", EvidenceUnit.BPS, bps, today, "spend_trends"),
            ],
            _action(ActionKind.OPEN, Screen.SPENDING),
            impact=result.total_change,
        )
    ]


# ── the engine ────────────────────────────────────────────────────────────────


def _visible_goals(session: Session, user_id: int) -> list[Goal]:
    """Active goals the person sees: the household's, and their own."""
    return list(
        session.execute(
            select(Goal)
            .where(
                Goal.status == GoalStatus.ACTIVE,
                or_(Goal.owner_user_id.is_(None), Goal.owner_user_id == user_id),
            )
            .order_by(Goal.id)
        ).scalars()
    )


def _goal_findings(session: Session, today: dt.date, goals: list[Goal]) -> list[Finding]:
    """Goals off track (ticket 111). Each goal is measured in its own scope, whoever asks."""
    found: list[Finding] = []
    for goal in goals:
        result = goal_analysis.progress(session, goal, today)
        subject = f"goal{goal.id}"
        goals_action = _action(ActionKind.OPEN, Screen.GOALS)
        if goal.kind is GoalKind.SPENDING_LIMIT:
            assert goal.target_amount is not None and result.month_to_date is not None
            category = session.get(Category, goal.category_id)
            name = category.name if category else goal.name
            limit, spent = goal.target_amount, result.month_to_date
            evidence = [
                _evidence("This month", EvidenceUnit.CENTS, spent, today, "goals.spending"),
                _evidence("Monthly limit", EvidenceUnit.CENTS, limit, today, "goals"),
            ]
            action = _action(ActionKind.OPEN, Screen.SPENDING, category_id=goal.category_id)
            if spent > limit:
                found.append(
                    _finding(
                        FindingKind.SPENDING_LIMIT_EXCEEDED,
                        f"{subject}:{today:%Y-%m}",
                        Severity.WARNING,
                        f"{name} is over its {_money(limit)} monthly limit",
                        f"{_money(spent)} spent this month so far.",
                        today,
                        evidence,
                        action,
                        impact=spent - limit,
                    )
                )
            elif not result.on_track:
                found.append(
                    _finding(
                        FindingKind.GOAL_OFF_TRACK,
                        f"{subject}:{today:%Y-%m}",
                        Severity.NOTICE,
                        f"{name} is on pace to pass its {_money(limit)} monthly limit",
                        f"{_money(spent)} spent this month so far, ahead of the month's pace.",
                        today,
                        evidence,
                        action,
                    )
                )
        elif goal.kind is GoalKind.EMERGENCY_FUND:
            assert goal.target_months is not None
            if result.on_track or result.runway_months_tenths is None:
                continue
            target = tenths(goal.target_months)
            found.append(
                _finding(
                    FindingKind.EMERGENCY_FUND_BELOW_TARGET,
                    subject,
                    Severity.WARNING,
                    f"Cash covers {Decimal(result.runway_months_tenths).scaleb(-1)} of the "
                    f"{Decimal(target).scaleb(-1)} months your emergency fund aims for",
                    "At the last six months' average spending, with no income.",
                    today,
                    [
                        _evidence(
                            "Runway",
                            EvidenceUnit.MONTHS_TENTHS,
                            result.runway_months_tenths,
                            today,
                            "goals.emergency_fund",
                            result.stale,
                        ),
                        _evidence("Target", EvidenceUnit.MONTHS_TENTHS, target, today, "goals"),
                    ],
                    goals_action,
                )
            )
        else:
            assert goal.target_amount is not None and result.saved is not None
            if result.on_track:
                continue
            evidence = [
                _evidence(
                    "Saved", EvidenceUnit.CENTS, result.saved, today, "goals.savings", result.stale
                ),
                _evidence("Target", EvidenceUnit.CENTS, goal.target_amount, today, "goals"),
            ]
            if result.monthly_needed is not None:
                evidence.append(
                    _evidence(
                        "Needed each month",
                        EvidenceUnit.CENTS,
                        result.monthly_needed,
                        today,
                        "goals.savings",
                        result.stale,
                    )
                )
            found.append(
                _finding(
                    FindingKind.GOAL_OFF_TRACK,
                    subject,
                    Severity.NOTICE,
                    f"{goal.name} is behind: {_money(result.saved)} of "
                    f"{_money(goal.target_amount)}",
                    "Behind the straight line from when the goal was set to its date.",
                    today,
                    evidence,
                    goals_action,
                    impact=result.monthly_needed,
                )
            )
    return found


def findings(session: Session, today: dt.date, view: ViewScope, user_id: int) -> list[Finding]:
    """Every finding for today, in one view, ranked: severity, then money at stake, then kind.

    Spend-based findings are the same in both views — spend is never split by ownership.
    """
    viewer_id = None if view is ViewScope.HOUSEHOLD else user_id
    goals = _visible_goals(session, user_id)
    # An emergency-fund goal sets the household's own threshold, so the default one stands
    # down: `emergency_fund_below_target` replaces `runway_low` whenever such a goal exists.
    has_fund = any(goal.kind is GoalKind.EMERGENCY_FUND for goal in goals)
    producers: list[Callable[[], list[Finding]]] = [
        lambda: _perks_expiring(session, today),
        lambda: _health_findings(session, today),
        lambda: _stale_balances(session, today, viewer_id),
        lambda: [] if has_fund else _runway_low(session, today, viewer_id),
        lambda: _goal_findings(session, today, goals),
        lambda: _spend_spikes(session, today),
        lambda: _recurring(session, today),
        lambda: _fees_uncovered(session, today),
        lambda: _net_worth_drop(session, today, viewer_id),
        lambda: _spend_increase(session, today),
    ]
    found = [finding for produce in producers for finding in produce()]
    found.sort(
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            -(f.impact_cents or 0),
            _KIND_ORDER[f.kind],
            f.id,
        )
    )
    return found
