"""Session cookies.

A signed, stateless cookie rather than a sessions table. The payload is a user id and
an expiry; there is nothing else a session needs to carry, and a table would add a
round trip to every request plus a row nobody ever reads for its own sake.

Signed with HMAC-SHA256 over the exact bytes that are sent, and compared in constant
time. The signature is what makes the cookie unforgeable — without it "user id 1" is a
value anyone can type.

Statelessness costs server-side revocation. That is the right trade here: the real gate
is Cloudflare Access, which revokes centrally and immediately, and rotating
`SESSION_SECRET` invalidates every cookie at once if it is ever needed.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json

#: The cookie name. Host-scoped with no `Domain` attribute, so it is never sent to a
#: sibling hostname — the demo deployment shares a registrable domain with the real one.
COOKIE_NAME = "pfa_session"


class SessionError(Exception):
    """A cookie that did not verify. Never shown to a user in detail."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue(user_id: int, secret: str, ttl_hours: int, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.UTC)
    payload = json.dumps(
        {"uid": user_id, "exp": int((now + dt.timedelta(hours=ttl_hours)).timestamp())},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    body = _b64(payload)
    return f"{body}.{_b64(_sign(body, secret))}"


def read(cookie: str, secret: str, now: dt.datetime | None = None) -> int:
    """The user id in a valid, unexpired cookie.

    Raises :class:`SessionError` for anything else — a bad signature, a mangled
    payload, and an expired session are all "not signed in", and distinguishing them to
    the caller only helps someone probing.
    """
    now = now or dt.datetime.now(dt.UTC)

    body, _, signature = cookie.partition(".")
    if not body or not signature:
        raise SessionError("Malformed session cookie")

    # Constant time: a byte-by-byte comparison leaks how much of a forged signature
    # was right, which is enough to construct one.
    if not hmac.compare_digest(_b64(_sign(body, secret)), signature):
        raise SessionError("Bad session signature")

    try:
        payload = json.loads(_unb64(body))
        user_id = int(payload["uid"])
        expires = int(payload["exp"])
    except Exception as error:
        raise SessionError("Unreadable session payload") from error

    if now.timestamp() >= expires:
        raise SessionError("Session expired")

    return user_id


def _sign(body: str, secret: str) -> bytes:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
