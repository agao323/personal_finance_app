"""`note_limitation`: the model says which data a question needed and the app lacks.

A no-op with a purpose. It reads nothing and changes nothing; its audit row is the record.
Counted over a month, those rows rank what to build next — holdings, liability terms, goals
— by the questions that actually needed them (docs/ADVISOR.md#tool-catalog). The answer
event lists the limitations noted, so the person sees what is missing, too.
"""

from __future__ import annotations

from pydantic import Field
from sqlalchemy.orm import Session

from app.advisor.tools import REGISTRY, ToolArgs, ToolContext, ToolResult
from app.schemas.advisor import LimitationKind


class NoteLimitationArgs(ToolArgs):
    capability: LimitationKind = Field(
        description=(
            "The data the question needed that the app does not have: holdings, "
            "tax_treatment, liability_terms, goals, credit_limits, reward_multipliers, "
            "credit_score, income_history, balance_history, transaction_coverage, "
            "projections, market_data (prices, rates, news), tax_or_legal_advice, or other."
        )
    )


class NoteLimitationResult(ToolResult):
    capability: LimitationKind
    noted: bool


@REGISTRY.tool(
    "note_limitation",
    description=(
        "Record that answering needs data this app does not have. Call it once per missing "
        "capability when a question cannot be fully answered — before saying what is missing "
        "— and never instead of a lookup that could answer. It reads and changes nothing."
    ),
    label=lambda args: f"Noted missing data: {args.capability.value.replace('_', ' ')}",
)
def note_limitation(
    args: NoteLimitationArgs, session: Session, ctx: ToolContext
) -> NoteLimitationResult:
    return NoteLimitationResult(capability=args.capability, noted=True)
