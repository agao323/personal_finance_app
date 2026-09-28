"""Debt tools: what each loan and card costs to carry. Ticket 112; 115 adds the strategies.

`debt_terms` lists every open liability with its balance and, where recorded, its terms: the
APR (to three decimals), the rate that applies today (a promotional one through its end date),
the minimum payment, the credit limit and utilisation, the term and maturity. A liability with
no terms says so, so the model can name the gap instead of guessing a rate.

**Balances follow the view** — `mine` is the asker's share, `household` every stake — through
the net worth service, which rounds once, per account. **Utilisation uses the whole balance**:
it describes the account against its limit, not anyone's share of it.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.tools import REGISTRY, ToolArgs, ToolContext, ToolResult
from app.models.account import Account
from app.models.enums import AccountKind, AccountSubtype
from app.schemas.common import ViewScope, to_cents
from app.services import liability_terms as terms_service
from app.services import net_worth as net_worth_service
from app.services.analysis.numbers import ratio_bps


class DebtTermsArgs(ToolArgs):
    view: ViewScope | None = Field(
        default=None,
        description="mine: your ownership share of each balance. household: every stake. "
        "Defaults to the conversation's view.",
    )


class DebtRow(BaseModel):
    account_id: int
    name_text: str
    subtype: AccountSubtype
    balance_cents: int = Field(description="The whole balance owed, before ownership.")
    share_cents: int = Field(description="The balance in this view: your share, or every stake.")
    balance_as_of: dt.date
    balance_stale: bool
    terms_recorded: bool
    apr_pct_thousandths: int | None = None
    today_apr_pct_thousandths: int | None = Field(
        default=None, description="The rate that applies today: a promotion through its end."
    )
    promo_apr_pct_thousandths: int | None = None
    promo_ends_on: dt.date | None = None
    minimum_payment_cents: int | None = None
    credit_limit_cents: int | None = None
    utilisation_bps: int | None = Field(
        default=None, description="The whole balance as a share of the credit limit."
    )
    term_months: int | None = None
    maturity_on: dt.date | None = None
    terms_as_of: dt.date | None = None
    terms_stale: bool | None = Field(
        default=None, description="The terms were last checked more than 365 days ago."
    )


class DebtTermsResult(ToolResult):
    debts: list[DebtRow]
    without_terms_count: int


@REGISTRY.tool(
    "debt_terms",
    description=(
        "Every open loan and card: its balance, and where recorded its APR, the rate that "
        "applies today, minimum payment, credit limit and utilisation, term and maturity. "
        "Call it for questions about interest, paying debt down, or credit utilisation. A "
        "debt with terms_recorded false has no rate on file: say so rather than assume one."
    ),
    label=lambda args: f"Debts and their terms{f', {args.view}' if args.view else ''}",
)
def debt_terms(args: DebtTermsArgs, session: Session, ctx: ToolContext) -> DebtTermsResult:
    viewer = ctx.viewer_id(args.view)
    worth = net_worth_service.net_worth(session, ctx.today, viewer)
    rows: list[DebtRow] = []
    for contribution in worth.contributions:
        if contribution.kind is not AccountKind.LIABILITY:
            continue
        account = session.get_one(Account, contribution.account_id)
        terms = terms_service.get(session, account.id)
        row = DebtRow(
            account_id=account.id,
            name_text=account.name,
            subtype=account.subtype,
            balance_cents=to_cents(contribution.raw_balance),
            share_cents=to_cents(contribution.adjusted_balance),
            balance_as_of=contribution.balance_as_of,
            balance_stale=contribution.is_stale,
            terms_recorded=terms is not None,
        )
        if terms is not None:
            row.apr_pct_thousandths = int(terms.apr.scaleb(3))
            row.today_apr_pct_thousandths = int(
                terms_service.effective_apr(terms, ctx.today).scaleb(3)
            )
            if terms.promo_apr is not None:
                row.promo_apr_pct_thousandths = int(terms.promo_apr.scaleb(3))
                row.promo_ends_on = terms.promo_ends_on
            if terms.minimum_payment is not None:
                row.minimum_payment_cents = to_cents(terms.minimum_payment)
            if terms.credit_limit is not None:
                row.credit_limit_cents = to_cents(terms.credit_limit)
                row.utilisation_bps = ratio_bps(contribution.raw_balance, terms.credit_limit)
            row.term_months = terms.term_months
            row.maturity_on = terms.maturity_on
            row.terms_as_of = terms.as_of
            row.terms_stale = terms_service.is_stale(terms, ctx.today)
        rows.append(row)
    return DebtTermsResult(
        as_of=ctx.today,
        view=args.view or ctx.view,
        stale=any(r.balance_stale or r.terms_stale for r in rows) or None,
        debts=rows,
        without_terms_count=sum(1 for r in rows if not r.terms_recorded),
    )
