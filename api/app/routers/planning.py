"""The planning profile and the stated assumptions. Ticket 109.

**Assumptions are append-only.** There is a route to list them and a route to add a version;
there is no route that changes or removes one, because a projection records the version it used
and must be reproducible with it. The latest version wins.

**A profile is its owner's alone.** The routes read and write the signed-in member's own row;
there is no member id in the path to point at anyone else's.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.models.planning import MemberProfile, PlanningAssumptions
from app.schemas.common import ErrorResponse, to_cents
from app.schemas.planning import (
    AssumptionsCreate,
    AssumptionsRead,
    MemberProfileRead,
    MemberProfileUpdate,
)
from app.services import planning as planning_service

router = APIRouter(
    prefix="/planning",
    tags=["planning"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


def _bps(pct: Decimal) -> int:
    return int(pct.scaleb(2))


def _pct(bps: int) -> Decimal:
    return Decimal(bps).scaleb(-2)


def to_read(row: PlanningAssumptions) -> AssumptionsRead:
    return AssumptionsRead(
        id=row.id,
        effective_from=row.effective_from,
        is_default=row.is_default,
        created_by_user_id=row.created_by_user_id,
        expected_real_return_bps=row.expected_real_return_bps,
        inflation_bps=row.inflation_bps,
        withdrawal_low_bps=row.withdrawal_low_bps,
        withdrawal_high_bps=row.withdrawal_high_bps,
        pre65_healthcare_annual_cents=(
            to_cents(row.pre65_healthcare_annual)
            if row.pre65_healthcare_annual is not None
            else None
        ),
        tax_deferred_withdrawal_tax_bps=row.tax_deferred_withdrawal_tax_bps,
        risk_tolerance=row.risk_tolerance,
        target_us_equity_bps=_bps(row.target_us_equity_pct),
        target_intl_equity_bps=_bps(row.target_intl_equity_pct),
        target_bonds_bps=_bps(row.target_bonds_pct),
        target_cash_bps=_bps(row.target_cash_pct),
        target_other_bps=_bps(row.target_other_pct),
    )


@router.get("/profile", response_model=MemberProfileRead)
def get_profile(session: DbSession, user: CurrentUser) -> MemberProfileRead:
    """Your birth year and target retirement year."""
    profile = session.get(MemberProfile, user.id)
    if profile is None:
        return MemberProfileRead()
    return MemberProfileRead(
        birth_year=profile.birth_year, target_retirement_year=profile.target_retirement_year
    )


@router.put("/profile", response_model=MemberProfileRead)
def put_profile(
    session: DbSession, user: CurrentUser, payload: MemberProfileUpdate
) -> MemberProfileRead:
    """Set your birth year and target retirement year. Only the year: nothing finer is needed."""
    profile = session.get(MemberProfile, user.id)
    if profile is None:
        profile = MemberProfile(user_id=user.id)
        session.add(profile)
    profile.birth_year = payload.birth_year
    profile.target_retirement_year = payload.target_retirement_year
    session.flush()
    return MemberProfileRead(
        birth_year=profile.birth_year, target_retirement_year=profile.target_retirement_year
    )


@router.get("/assumptions", response_model=list[AssumptionsRead])
def list_assumptions(session: DbSession, user: CurrentUser) -> list[AssumptionsRead]:
    """Every version, newest first. The first is the one in force."""
    return [to_read(row) for row in planning_service.assumption_versions(session)]


@router.post("/assumptions", response_model=AssumptionsRead, status_code=status.HTTP_201_CREATED)
def add_assumptions(
    session: DbSession, user: CurrentUser, payload: AssumptionsCreate
) -> AssumptionsRead:
    """State a new version. The previous ones stay, unchanged."""
    row = PlanningAssumptions(
        is_default=False,
        created_by_user_id=user.id,
        expected_real_return_bps=payload.expected_real_return_bps,
        inflation_bps=payload.inflation_bps,
        withdrawal_low_bps=payload.withdrawal_low_bps,
        withdrawal_high_bps=payload.withdrawal_high_bps,
        pre65_healthcare_annual=(
            Decimal(payload.pre65_healthcare_annual_cents).scaleb(-2)
            if payload.pre65_healthcare_annual_cents is not None
            else None
        ),
        tax_deferred_withdrawal_tax_bps=payload.tax_deferred_withdrawal_tax_bps,
        risk_tolerance=payload.risk_tolerance,
        target_us_equity_pct=_pct(payload.target_us_equity_bps),
        target_intl_equity_pct=_pct(payload.target_intl_equity_bps),
        target_bonds_pct=_pct(payload.target_bonds_bps),
        target_cash_pct=_pct(payload.target_cash_bps),
        target_other_pct=_pct(payload.target_other_bps),
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return to_read(row)
