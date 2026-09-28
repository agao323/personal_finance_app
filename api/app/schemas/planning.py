"""The planning profile and assumptions over the wire.

Rates and the target mix are basis points (4000 is 40.00%); money is cents. The mix must total
exactly 10,000 basis points — 100%.
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field, model_validator

from app.models.enums import RiskTolerance
from app.schemas.common import Cents, Schema

Bps = int


class MemberProfileRead(Schema):
    """The signed-in member's own profile. Nobody reads anyone else's."""

    birth_year: int | None = None
    target_retirement_year: int | None = None


class MemberProfileUpdate(Schema):
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    target_retirement_year: int | None = Field(default=None, ge=1900, le=2200)

    @model_validator(mode="after")
    def _retire_after_birth(self) -> MemberProfileUpdate:
        if (
            self.birth_year is not None
            and self.target_retirement_year is not None
            and self.target_retirement_year <= self.birth_year
        ):
            raise ValueError("A retirement year comes after the birth year.")
        return self


class _Assumptions(Schema):
    expected_real_return_bps: Bps = Field(ge=-1000, le=2000, description="After inflation.")
    inflation_bps: Bps = Field(ge=-500, le=2000)
    withdrawal_low_bps: Bps = Field(ge=0, le=1500)
    withdrawal_high_bps: Bps = Field(ge=0, le=1500)
    pre65_healthcare_annual_cents: Cents | None = Field(
        default=None, ge=0, description="A year of healthcare before Medicare. Null: not stated."
    )
    tax_deferred_withdrawal_tax_bps: Bps = Field(
        ge=0, le=6000, description="A flat effective rate — a simplification, stated as one."
    )
    risk_tolerance: RiskTolerance
    target_us_equity_bps: Bps = Field(ge=0, le=10000)
    target_intl_equity_bps: Bps = Field(ge=0, le=10000)
    target_bonds_bps: Bps = Field(ge=0, le=10000)
    target_cash_bps: Bps = Field(ge=0, le=10000)
    target_other_bps: Bps = Field(ge=0, le=10000)


class AssumptionsRead(_Assumptions):
    id: int
    effective_from: dt.datetime
    is_default: bool = Field(description="The defaults the app started with; nobody set these.")
    created_by_user_id: int | None = None


class AssumptionsCreate(_Assumptions):
    """A new version. Every field is stated; the previous version stays, unchanged."""

    @model_validator(mode="after")
    def _consistent(self) -> AssumptionsCreate:
        if self.withdrawal_low_bps > self.withdrawal_high_bps:
            raise ValueError("The low withdrawal rate cannot be above the high one.")
        total = (
            self.target_us_equity_bps
            + self.target_intl_equity_bps
            + self.target_bonds_bps
            + self.target_cash_bps
            + self.target_other_bps
        )
        if total != 10000:
            whole, rest = divmod(total, 100)
            raise ValueError(f"The target mix must total 100%; it totals {whole}.{rest:02d}%.")
        return self
