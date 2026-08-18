"""Burn rate and months of runway."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import Cents, Schema


class BurnWindow(Schema):
    months: int = Field(description="Trailing window length: 3, 6, or 12.")
    average_monthly_spend_cents: Cents
    months_of_runway: float | None = Field(
        default=None, description="Null when average spend is zero."
    )


class RunwayRead(Schema):
    """Gross spend, excluding transfers. Income is not netted off.

    Gross answers "how long if income stopped", which is the question runway is for.
    Netting income in would make the number meaningless while employed.
    """

    liquid_assets_cents: Cents = Field(description="Ownership-adjusted, kind='liquid_asset' only.")
    windows: list[BurnWindow]
    partial_month_excluded: bool = Field(
        description=(
            "True when the current, incomplete month was left out. Averaging it in "
            "makes burn look artificially low every month."
        )
    )
