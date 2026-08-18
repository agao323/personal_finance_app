"""Passkey authentication. Implemented by ticket 034.

No password endpoints exist, deliberately. See docs/SECURITY.md#auth.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.auth import (
    AuthenticationOptions,
    AuthenticationVerify,
    RegistrationOptions,
    RegistrationVerify,
    SessionRead,
)
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"], responses={401: {"model": ErrorResponse}})


@router.post("/register/options", response_model=RegistrationOptions)
def registration_options(session: DbSession, user: CurrentUser) -> RegistrationOptions:
    not_implemented("034")


@router.post("/register/verify", response_model=SessionRead)
def registration_verify(
    session: DbSession, user: CurrentUser, payload: RegistrationVerify
) -> SessionRead:
    not_implemented("034")


@router.post("/login/options", response_model=AuthenticationOptions)
def authentication_options(session: DbSession) -> AuthenticationOptions:
    not_implemented("034")


@router.post("/login/verify", response_model=SessionRead)
def authentication_verify(session: DbSession, payload: AuthenticationVerify) -> SessionRead:
    not_implemented("034")


@router.get("/session", response_model=SessionRead)
def read_session(user: CurrentUser) -> SessionRead:
    not_implemented("034")
