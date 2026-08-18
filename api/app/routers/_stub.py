"""The 501 stub every Wave 2 route starts as.

A route that exists, is typed, and refuses to run is what lets Lane C build a screen
against a shape Lane A has not implemented yet. The alternative — declaring routes as
each lane reaches them — is exactly the drift this ticket exists to prevent.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def not_implemented(ticket: str) -> NoReturn:
    """Raise a 501 naming the ticket that will implement this route."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented yet — ticket {ticket}.",
    )
