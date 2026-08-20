"""Verifying Cloudflare Access assertions at the API.

The web tier already does this in `web/src/lib/access.ts` and refuses anything that
fails. This is not that check repeated for its own sake — it exists because **one route
trusts Access as the sole factor**: account recovery, where somebody who has lost their
passkey has no session and no second credential to offer.

For that route the assertion is the credential, so it has to be verified *here*, by the
service that acts on it, rather than inferred from a header the web tier attached. The
API has no public address, but "unreachable" and "unauthenticated" are different
properties and only one of them is enforced by a network.

**Unconfigured means disabled, and disabled means recovery is refused** — never
"allowed without a check". That distinction is the whole security of the recovery
route: locally, and anywhere Access is not in front, there is nothing to verify and so
nothing may be recovered.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.config import get_settings

#: The header Cloudflare Access adds once it has authenticated someone.
ASSERTION_HEADER = "cf-access-jwt-assertion"


class AccessError(Exception):
    """The assertion is missing, malformed, or not ours. Never shown in detail."""


@dataclass(frozen=True)
class AccessConfig:
    team_domain: str
    audience: str

    @property
    def issuer(self) -> str:
        return f"https://{self.team_domain}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/cdn-cgi/access/certs"


def configured() -> AccessConfig | None:
    """The Access configuration, or None when this deployment has no Access in front.

    Both values or neither. An audience with no issuer accepts a token from any Access
    tenant, and an issuer with no audience accepts one minted for a different
    application — either alone is worse than nothing, because it looks like a check.
    """
    settings = get_settings()
    team_domain = (settings.cf_access_team_domain or "").replace("https://", "").rstrip("/")
    audience = settings.cf_access_aud or ""
    if not team_domain or not audience:
        return None
    return AccessConfig(team_domain=team_domain, audience=audience)


#: Cached per JWKS URL. Refetching Cloudflare's keys on every request is a denial of
#: service aimed at yourself; PyJWKClient handles the caching and the rotation.
_clients: dict[str, PyJWKClient] = {}


def _client(config: AccessConfig) -> PyJWKClient:
    client = _clients.get(config.jwks_url)
    if client is None:
        client = PyJWKClient(config.jwks_url, cache_keys=True)
        _clients[config.jwks_url] = client
    return client


def verified_email(assertion: str | None) -> str:
    """The email Cloudflare Access authenticated, or raise.

    Signature, issuer and audience are all checked. A decoded-but-unverified JWT is a
    header anyone can write, which is precisely the attack this route would otherwise
    be wide open to.
    """
    config = configured()
    if config is None:
        raise AccessError("Access is not configured for this deployment")
    if not assertion:
        raise AccessError("No Access assertion")

    try:
        key = _client(config).get_signing_key_from_jwt(assertion).key
        payload = jwt.decode(
            assertion,
            key=key,
            algorithms=["RS256"],
            audience=config.audience,
            issuer=config.issuer,
        )
    except Exception as error:  # a family of jwt validation errors
        raise AccessError(f"Assertion did not verify: {error}") from error

    email = payload.get("email")
    if not isinstance(email, str) or not email:
        raise AccessError("Assertion carries no email")
    return email
