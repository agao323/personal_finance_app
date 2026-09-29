"""Planning assumption queries (ticket 109). Append-only: the latest version is in force."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning import PlanningAssumptions


def assumption_versions(session: Session) -> list[PlanningAssumptions]:
    """Every version, newest first. The first is the one in force."""
    return list(
        session.execute(
            select(PlanningAssumptions).order_by(
                PlanningAssumptions.effective_from.desc(), PlanningAssumptions.id.desc()
            )
        ).scalars()
    )
