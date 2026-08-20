"""Passkey authentication.

No password endpoints exist, deliberately. See docs/SECURITY.md#auth.

**The `users` table is the allowlist.** There is no separate list of who may sign in —
a second list is a second thing to keep in step, and the failure mode is someone
removed from one and not the other. Registration is refused for an address that is not
an active user, and it is refused with the same message a wrong address gets, so the
endpoint does not report whether a given email is in the household.

Route docstrings are part of the frozen contract — see the note in `routers/rules.py`.
Reasoning lives here and in `services/webauthn.py`.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.deps import CurrentIdentity, CurrentUser, DbSession
from app.models.user import Credential, Invitation, User, WebAuthnChallenge
from app.routers import users
from app.schemas.auth import (
    AuthenticationOptions,
    AuthenticationVerify,
    CredentialRead,
    InvitationRedeemOptions,
    InvitationRedeemVerify,
    RegistrationOptions,
    RegistrationVerify,
    SessionRead,
)
from app.schemas.common import ErrorResponse
from app.services import access, webauthn
from app.services import session as sessions

router = APIRouter(prefix="/auth", tags=["auth"], responses={401: {"model": ErrorResponse}})

REGISTER = "register"
AUTHENTICATE = "authenticate"

#: One message for every failed ceremony. Distinguishing "no such user" from "wrong
#: authenticator" tells an attacker which addresses are in the household.
REFUSED = "Could not verify that passkey"

#: One message for every invitation failure — unknown, expired, already spent. The
#: token is the secret, and saying which of those you hit is a way to probe it.
INVITATION_REFUSED = "That invitation is not valid"

#: One message whether Access is unconfigured, the assertion failed, or the identity is
#: not in the household. Which of those you hit is not a probe worth answering.
RECOVERY_REFUSED = "Account recovery is not available for this identity"


def _issue_challenge(session: DbSession, purpose: str, user_id: int | None) -> webauthn.Ceremony:
    ceremony = webauthn.new_ceremony()
    # Sweep expired rows here rather than on a schedule: this table holds a handful of
    # rows for one household, and a cron for that is more moving parts than the
    # problem has.
    session.execute(
        delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < dt.datetime.now(dt.UTC))
    )
    session.add(
        WebAuthnChallenge(
            challenge_id=ceremony.challenge_id,
            challenge=ceremony.challenge,
            purpose=purpose,
            user_id=user_id,
            expires_at=ceremony.expires_at,
        )
    )
    session.flush()
    return ceremony


def _spend_challenge(session: DbSession, challenge_id: str, purpose: str) -> bytes:
    """Consume a challenge, or refuse.

    Deleted on read, so a challenge answered twice fails the second time — which is
    the entire point of a challenge.
    """
    row = session.execute(
        select(WebAuthnChallenge).where(WebAuthnChallenge.challenge_id == challenge_id)
    ).scalar_one_or_none()

    if row is None or row.purpose != purpose or webauthn.is_expired(row.expires_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    challenge = row.challenge
    session.delete(row)
    session.flush()
    return challenge


def _set_cookie(response: Response, user_id: int, credential_id: int | None = None) -> None:
    settings = get_settings()
    response.set_cookie(
        sessions.COOKIE_NAME,
        sessions.issue(
            user_id,
            settings.session_secret,
            settings.session_ttl_hours,
            credential_id=credential_id,
        ),
        httponly=True,
        secure=settings.cookie_secure,
        # `lax`, not `strict`: the Cloudflare Access redirect returns the user
        # cross-site, and `strict` drops the cookie on exactly that navigation.
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


@router.post("/register/options", response_model=RegistrationOptions)
def registration_options(session: DbSession, user: CurrentUser) -> RegistrationOptions:
    settings = get_settings()
    ceremony = _issue_challenge(session, REGISTER, user.id)
    existing = list(
        session.execute(
            select(Credential.credential_id).where(Credential.user_id == user.id)
        ).scalars()
    )

    return RegistrationOptions(
        options=webauthn.registration_options(
            rp_id=settings.rp_id,
            rp_name=settings.rp_name,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            challenge=ceremony.challenge,
            existing_credential_ids=existing,
        ),
        challenge_id=ceremony.challenge_id,
    )


@router.post("/register/verify", response_model=SessionRead)
def registration_verify(
    session: DbSession, user: CurrentUser, payload: RegistrationVerify, response: Response
) -> SessionRead:
    settings = get_settings()
    challenge = _spend_challenge(session, payload.challenge_id, REGISTER)

    try:
        registered = webauthn.verify_registration(
            credential=payload.credential,
            challenge=challenge,
            rp_id=settings.rp_id,
            origin=settings.web_origin,
        )
    except webauthn.WebAuthnError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from error

    stored = Credential(
        user_id=user.id,
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=registered.sign_count,
    )
    session.add(stored)
    session.flush()

    _set_cookie(response, user.id, credential_id=stored.id)
    return SessionRead(user_id=user.id, email=user.email, display_name=user.display_name)


@router.post("/login/options", response_model=AuthenticationOptions)
def authentication_options(session: DbSession) -> AuthenticationOptions:
    settings = get_settings()
    ceremony = _issue_challenge(session, AUTHENTICATE, None)

    return AuthenticationOptions(
        options=webauthn.authentication_options(rp_id=settings.rp_id, challenge=ceremony.challenge),
        challenge_id=ceremony.challenge_id,
    )


@router.post("/login/verify", response_model=SessionRead)
def authentication_verify(
    session: DbSession, payload: AuthenticationVerify, response: Response
) -> SessionRead:
    settings = get_settings()
    challenge = _spend_challenge(session, payload.challenge_id, AUTHENTICATE)

    try:
        credential_id = webauthn.credential_id_from(payload.credential)
    except webauthn.WebAuthnError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from error

    stored = session.execute(
        select(Credential).where(Credential.credential_id == credential_id)
    ).scalar_one_or_none()
    if stored is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    user = session.get(User, stored.user_id)
    # The allowlist check, at the only moment it matters. Deactivating a user is what
    # revokes their access; their passkey still exists and still verifies.
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    try:
        new_count = webauthn.verify_authentication(
            credential=payload.credential,
            challenge=challenge,
            rp_id=settings.rp_id,
            origin=settings.web_origin,
            public_key=stored.public_key,
            stored_sign_count=stored.sign_count,
        )
    except webauthn.WebAuthnError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from error

    if not webauthn.sign_count_is_valid(stored.sign_count, new_count):
        # A counter that did not advance means the credential was cloned, or this
        # assertion is a replay. Both are refused, and the credential is left in place
        # rather than deleted — destroying it on a signal that can also be a buggy
        # authenticator would lock the household out of its own app.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    stored.sign_count = new_count
    stored.last_used_at = dt.datetime.now(dt.UTC)
    session.flush()

    _set_cookie(response, user.id, credential_id=stored.id)
    return SessionRead(user_id=user.id, email=user.email, display_name=user.display_name)


@router.get("/session", response_model=SessionRead)
def read_session(user: CurrentUser) -> SessionRead:
    return SessionRead(user_id=user.id, email=user.email, display_name=user.display_name)


def _invited_user(session: DbSession, token: str) -> User:
    """The account an invitation belongs to, or a refusal.

    Every failure — unknown, expired, already redeemed — returns the same message. The
    token is the secret; telling someone which of those they hit is a way to probe it.
    """
    row = session.execute(
        select(Invitation).where(Invitation.token_hash == users.hash_token(token))
    ).scalar_one_or_none()

    if row is None or row.redeemed_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVITATION_REFUSED)
    if webauthn.is_expired(row.expires_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVITATION_REFUSED)

    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVITATION_REFUSED)
    return user


@router.post("/invitation/redeem/options", response_model=RegistrationOptions)
def invitation_options(session: DbSession, payload: InvitationRedeemOptions) -> RegistrationOptions:
    """Options for registering a passkey against an invited account.

    Takes no `CurrentUser`, deliberately. The whole point is that the invited person
    has no session yet — and if it took the *current* user, an owner clicking this
    would attach the newcomer's authenticator to their own account, which is silently
    wrong in the way that matters most: every ownership figure is per-user.

    Still behind Cloudflare Access on the real deployment, so the token is a second
    factor rather than the only one.
    """
    settings = get_settings()
    invited = _invited_user(session, payload.token)
    ceremony = _issue_challenge(session, REGISTER, invited.id)

    return RegistrationOptions(
        options=webauthn.registration_options(
            rp_id=settings.rp_id,
            rp_name=settings.rp_name,
            user_id=invited.id,
            email=invited.email,
            display_name=invited.display_name,
            challenge=ceremony.challenge,
            existing_credential_ids=[],
        ),
        challenge_id=ceremony.challenge_id,
    )


@router.post("/invitation/redeem/verify", response_model=SessionRead)
def invitation_verify(
    session: DbSession, payload: InvitationRedeemVerify, response: Response
) -> SessionRead:
    """Register the passkey, mark the invitation spent, and sign them in.

    The credential is attached to the **invited** user, read from the token — never to
    whoever happens to be holding a session in this browser.
    """
    settings = get_settings()
    invited = _invited_user(session, payload.token)
    challenge = _spend_challenge(session, payload.challenge_id, REGISTER)

    try:
        registered = webauthn.verify_registration(
            credential=payload.credential,
            challenge=challenge,
            rp_id=settings.rp_id,
            origin=settings.web_origin,
        )
    except webauthn.WebAuthnError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from error

    stored = Credential(
        user_id=invited.id,
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=registered.sign_count,
    )
    session.add(stored)

    # Spent, not deleted: a redeemed invitation is a fact worth being able to see, and
    # marking it is what makes a second attempt fail rather than silently work.
    invitation = session.execute(
        select(Invitation).where(Invitation.token_hash == users.hash_token(payload.token))
    ).scalar_one()
    invitation.redeemed_at = dt.datetime.now(dt.UTC)
    session.flush()

    _set_cookie(response, invited.id, credential_id=stored.id)
    return SessionRead(user_id=invited.id, email=invited.email, display_name=invited.display_name)


def _recovering_user(session: DbSession, request: Request) -> User:
    """The account Cloudflare Access says you are, for recovery only.

    This is the one place the application treats Access as sufficient on its own, and
    it is what ADR 0002 has always described: "a lost passkey is recovered by
    re-registering from behind Access". Somebody who has lost their only device has no
    session and no second credential, so Access is the only thing left that knows who
    they are — and it is the layer this project calls the security in the first place.

    Refused outright when Access is not configured. Locally there is nothing in front
    of the app, so an unguarded version of this would be a free "register as anybody"
    endpoint.
    """
    try:
        email = access.verified_email(request.headers.get(access.ASSERTION_HEADER))
    except access.AccessError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=RECOVERY_REFUSED) from error

    user = session.execute(
        select(User).where(func.lower(User.email) == email.lower())
    ).scalar_one_or_none()
    # The `users` table is still the allowlist. Passing Access is necessary and not
    # sufficient: an identity Cloudflare authenticated but this household never added
    # gets the same refusal as a forged assertion.
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=RECOVERY_REFUSED)
    return user


@router.post("/recover/options", response_model=RegistrationOptions)
def recover_options(session: DbSession, request: Request) -> RegistrationOptions:
    """Begin registering a replacement passkey, identified only by Cloudflare Access."""
    settings = get_settings()
    user = _recovering_user(session, request)
    ceremony = _issue_challenge(session, REGISTER, user.id)

    existing = list(
        session.execute(
            select(Credential.credential_id).where(Credential.user_id == user.id)
        ).scalars()
    )

    return RegistrationOptions(
        options=webauthn.registration_options(
            rp_id=settings.rp_id,
            rp_name=settings.rp_name,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            challenge=ceremony.challenge,
            existing_credential_ids=existing,
        ),
        challenge_id=ceremony.challenge_id,
    )


@router.post("/recover/verify", response_model=SessionRead)
def recover_verify(
    session: DbSession, request: Request, payload: RegistrationVerify, response: Response
) -> SessionRead:
    """Register the replacement passkey and sign them in.

    The Access assertion is verified **again** here rather than trusting that the
    challenge was issued to the right person. The challenge id travels through the
    browser, and a check that happens only on the way out is a check somebody can walk
    around.

    The old credentials are deliberately left in place. A lost phone that turns up in a
    coat pocket still works, and anything genuinely gone can be removed from the
    passkeys screen once you are back in — which is a decision to make while signed in,
    not while panicking.
    """
    settings = get_settings()
    user = _recovering_user(session, request)
    challenge = _spend_challenge(session, payload.challenge_id, REGISTER)

    try:
        registered = webauthn.verify_registration(
            credential=payload.credential,
            challenge=challenge,
            rp_id=settings.rp_id,
            origin=settings.web_origin,
        )
    except webauthn.WebAuthnError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REFUSED) from error

    stored = Credential(
        user_id=user.id,
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=registered.sign_count,
    )
    session.add(stored)
    session.flush()

    _set_cookie(response, user.id, credential_id=stored.id)
    return SessionRead(user_id=user.id, email=user.email, display_name=user.display_name)


@router.get("/credentials", response_model=list[CredentialRead])
def list_credentials(
    session: DbSession, user: CurrentUser, identity: CurrentIdentity
) -> list[CredentialRead]:
    """The passkeys registered to you, newest last."""
    rows = list(
        session.execute(
            select(Credential).where(Credential.user_id == user.id).order_by(Credential.created_at)
        ).scalars()
    )

    return [
        CredentialRead(
            id=row.id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            is_current=row.id == identity.credential_id,
        )
        for row in rows
    ]


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(session: DbSession, user: CurrentUser, credential_id: int) -> Response:
    """Remove a passkey.

    Removing the last one is refused. An account with no credential can only be
    recovered through the bootstrap window, and that window is closed for good the
    moment any credential exists — so this would be a lockout wearing the word
    "remove", and there is no undo behind it.
    """
    credential = session.get(Credential, credential_id)
    # Same 404 for "not yours" as for "does not exist": whether a given id belongs to
    # someone else is not a question this endpoint should answer.
    if credential is None or credential.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such passkey")

    remaining = session.execute(
        select(func.count()).select_from(Credential).where(Credential.user_id == user.id)
    ).scalar_one()
    if remaining <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This is your only passkey. Register another device before removing it.",
        )

    session.delete(credential)
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    """Clear the session cookie."""
    # Built here rather than mutating an injected Response: returning a *different*
    # response than the one the cookie was set on discards the header silently, which
    # is exactly the bug the test for this caught.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(sessions.COOKIE_NAME, path="/")
    return response
