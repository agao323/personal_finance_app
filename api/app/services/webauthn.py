"""WebAuthn ceremonies.

Registration and authentication, wrapping the `webauthn` library so the routes stay
thin and the parts worth testing are pure functions.

Three decisions that are easy to get wrong and expensive to discover late:

**The RP ID is the registrable parent domain**, never the app's hostname. A credential
scoped to `app.example.com` is unusable from `example.com`, so moving the app — which
this project already did once — silently invalidates every passkey. The failure appears
only in production, on the day you move.

**Sign count going backwards means a cloned authenticator.** Authenticators that
implement a counter increment it every assertion; a value that does not advance past
what we stored is either a clone or a replay, and both are rejected. Authenticators
that report a constant zero are not implementing the counter at all, which is allowed
by the spec and must not be treated as an attack.

**Challenges are single-use and expire.** They live in a table with the ceremony they
belong to, are deleted on use, and are rejected once stale — a challenge that can be
replayed is not a challenge.
"""

from __future__ import annotations

import base64
import datetime as dt
import secrets
from dataclasses import dataclass
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

#: How long a ceremony may sit unfinished. Long enough for a fumbled Touch ID, short
#: enough that a challenge captured off a screen is worthless by the time it is used.
CHALLENGE_TTL = dt.timedelta(minutes=5)


class WebAuthnError(Exception):
    """A ceremony that did not verify. The message is safe to show a user."""


@dataclass(frozen=True)
class Ceremony:
    """A challenge issued to a browser, waiting to be answered."""

    challenge_id: str
    challenge: bytes
    expires_at: dt.datetime


def new_ceremony(now: dt.datetime | None = None) -> Ceremony:
    now = now or dt.datetime.now(dt.UTC)
    return Ceremony(
        challenge_id=secrets.token_urlsafe(24),
        challenge=secrets.token_bytes(32),
        expires_at=now + CHALLENGE_TTL,
    )


def is_expired(expires_at: dt.datetime, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.UTC)
    # Rows read back from Postgres carry a timezone; a naive value would raise on
    # comparison, and defaulting it to UTC is right for a column declared UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    return now >= expires_at


def registration_options(
    *,
    rp_id: str,
    rp_name: str,
    user_id: int,
    email: str,
    display_name: str,
    challenge: bytes,
    existing_credential_ids: list[bytes],
) -> dict[str, Any]:
    """Options for `navigator.credentials.create()`.

    `exclude_credentials` stops the same authenticator registering twice against one
    user, which would otherwise produce two rows that behave identically and one of
    them silently stale.
    """
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=str(user_id).encode(),
        user_name=email,
        user_display_name=display_name,
        challenge=challenge,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=credential_id)
            for credential_id in existing_credential_ids
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return _as_dict(options_to_json(options))


def authentication_options(*, rp_id: str, challenge: bytes) -> dict[str, Any]:
    """Options for `navigator.credentials.get()`.

    No `allow_credentials`: the login page does not know who is signing in, and listing
    every registered credential id there would leak the household's authenticator set
    to anyone who loaded the page.
    """
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return _as_dict(options_to_json(options))


@dataclass(frozen=True)
class RegisteredCredential:
    credential_id: bytes
    public_key: bytes
    sign_count: int


def verify_registration(
    *,
    credential: dict[str, Any],
    challenge: bytes,
    rp_id: str,
    origin: str,
) -> RegisteredCredential:
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except Exception as error:  # the library raises a family of validation errors
        raise WebAuthnError(f"Registration could not be verified: {error}") from error

    return RegisteredCredential(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
    )


def verify_authentication(
    *,
    credential: dict[str, Any],
    challenge: bytes,
    rp_id: str,
    origin: str,
    public_key: bytes,
    stored_sign_count: int,
) -> int:
    """Verify an assertion and return the new sign count."""
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=public_key,
            credential_current_sign_count=stored_sign_count,
        )
    except Exception as error:
        raise WebAuthnError(f"Sign-in could not be verified: {error}") from error

    return verified.new_sign_count


def sign_count_is_valid(stored: int, presented: int) -> bool:
    """Whether a presented counter is acceptable.

    An authenticator that implements the counter increments it on every assertion, so
    a value that fails to advance is a clone or a replay. An authenticator that does
    not implement it reports zero forever — permitted by the spec, and treating that as
    an attack would lock out a whole class of hardware for no gain.
    """
    if stored == 0 and presented == 0:
        return True
    return presented > stored


def credential_id_from(credential: dict[str, Any]) -> bytes:
    """The raw credential id out of a client's JSON payload."""
    raw = credential.get("rawId") or credential.get("id")
    if not isinstance(raw, str):
        raise WebAuthnError("The credential is missing its id.")
    return base64url_decode(raw)


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _as_dict(payload: str) -> dict[str, Any]:
    import json

    parsed: dict[str, Any] = json.loads(payload)
    return parsed
