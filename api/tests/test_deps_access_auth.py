"""Cloudflare Access as the authentication (ticket 047a).

Every test here is about a way this could **fail open**, which is the whole reason 047
was split: the change in this half can be silently wrong, and the deletion in 047b
cannot. See docs/adr/0007-drop-passkeys.md.

The suite as a whole runs authenticated by a development identity, so these tests spend
most of their effort taking that away and putting a real assertion in its place.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import access

OWNER = "owner@example.invalid"


@pytest.fixture
def behind_access(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Configure Access, and remove the development identity it replaces.

    Both halves matter. Leaving the dev identity in place would let a test pass because
    of the fallback rather than the assertion under test — which is exactly the shape of
    mistake that would make this file worthless.
    """
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "allofmymoney.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-123")
    monkeypatch.delenv("DEV_IDENTITY_EMAIL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _assertion_verifies_as(monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    """Stand in for Cloudflare having verified a token as `email`.

    The signature, issuer and audience checks are `access.verified_email`'s own and are
    tested in test_recovery.py. What is under test here is what `deps` does with the
    answer.
    """
    monkeypatch.setattr(access, "verified_email", lambda _assertion: email)


# ── the identity has to be a member ──────────────────────────────────────────


def test_an_authenticated_stranger_is_refused(
    client: TestClient, behind_access: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Access authenticated them; this household never added them.

    The `users` table is the authorisation and this is the test that says so. Without
    it, an Access policy written one line too broadly would be a total compromise
    rather than a refused request — which is why ADR 0007 made keeping this table a
    condition of removing the passkey layer.
    """
    _assertion_verifies_as(monkeypatch, "stranger@example.invalid")

    response = client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"})

    assert response.status_code == 401


def test_a_deactivated_member_is_refused_on_the_next_request(
    client: TestClient,
    db_session: Session,
    owner_id: int,
    behind_access: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`is_active` is read per request, not trusted from when something was issued."""
    _assertion_verifies_as(monkeypatch, OWNER)
    assert client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"}).status_code == 200

    db_session.execute(text("UPDATE users SET is_active = false WHERE id = :i"), {"i": owner_id})

    assert client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"}).status_code == 401


@pytest.mark.parametrize(
    "variant",
    [OWNER, OWNER.upper(), "Owner@Example.Invalid", f"  {OWNER}  ", f"{OWNER}\n"],
)
def test_the_email_is_matched_leniently(
    client: TestClient, behind_access: None, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    """Cloudflare returns whatever the identity provider gave it.

    An allowlist that misses on `Owner@` where the row says `owner@` fails closed and
    looks like a bug in Access rather than a bug here — the most expensive kind to
    diagnose, and one this project has already paid for once with the team domain.
    """
    _assertion_verifies_as(monkeypatch, variant)

    response = client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"})

    assert response.status_code == 200


# ── no assertion, or one that does not verify ────────────────────────────────


def test_a_missing_assertion_is_refused(client: TestClient, behind_access: None) -> None:
    assert client.get("/auth/session").status_code == 401


def test_an_unverifiable_assertion_is_refused(
    client: TestClient, behind_access: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoded-but-unverified JWT is a header anyone can write."""

    def _raise(_assertion: str | None) -> str:
        raise access.AccessError("Assertion did not verify: signature")

    monkeypatch.setattr(access, "verified_email", _raise)

    assert client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"}).status_code == 401


def test_the_refusal_never_says_which_check_failed(
    client: TestClient, behind_access: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown identity and an unverifiable token are indistinguishable from outside.

    Distinguishing them tells an attacker which half they got right. The log tells the
    operator, who is the only one who needs to know.
    """

    def _raise(_assertion: str | None) -> str:
        raise access.AccessError("Assertion did not verify: signature")

    _assertion_verifies_as(monkeypatch, "stranger@example.invalid")
    stranger = client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"})

    monkeypatch.setattr(access, "verified_email", _raise)
    forged = client.get("/auth/session", headers={access.ASSERTION_HEADER: "tok"})

    assert stranger.status_code == forged.status_code == 401
    assert stranger.json() == forged.json()


# ── the development identity, and the ways it must not escape ────────────────


def test_the_development_identity_signs_you_in_locally(client: TestClient) -> None:
    """The default state of the suite, asserted once so it is a decision not an accident."""
    assert access.configured() is None
    assert get_settings().is_deployment is False

    assert client.get("/auth/session").status_code == 200


def test_the_development_identity_is_ignored_on_a_deployment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting it on a deployed environment must not become a way in.

    The startup guard in `main.lifespan` should stop this configuration existing at all.
    This asserts the second guard behind it, because a check that lives in one place
    lives there only until someone edits that place.
    """
    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    monkeypatch.setenv("DEV_IDENTITY_EMAIL", OWNER)
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    get_settings.cache_clear()

    assert client.get("/auth/session").status_code == 401

    get_settings.cache_clear()


def test_the_development_identity_is_ignored_when_access_is_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With Access in front, the assertion is the only thing that speaks.

    Otherwise a stray `DEV_IDENTITY_EMAIL` in a deployed environment would authenticate
    every request that arrived without a token.
    """
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "allofmymoney.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-123")
    monkeypatch.setenv("DEV_IDENTITY_EMAIL", OWNER)
    get_settings.cache_clear()

    assert client.get("/auth/session").status_code == 401

    get_settings.cache_clear()


def test_an_unknown_development_identity_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It names an identity; it does not create one. The `users` table still decides."""
    monkeypatch.setenv("DEV_IDENTITY_EMAIL", "nobody@example.invalid")
    get_settings.cache_clear()

    assert client.get("/auth/session").status_code == 401

    get_settings.cache_clear()


# ── the demo ─────────────────────────────────────────────────────────────────


def test_the_demo_serves_its_identity_without_an_assertion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo is public and has no Access in front of it.

    Until 047a this worked by accident — its `credentials` table was empty, so the
    bootstrap window never closed and every visitor got the seeded user. That accident
    died with the bootstrap window, so the behaviour is asserted rather than inherited.
    """
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("DEV_IDENTITY_EMAIL", raising=False)
    get_settings.cache_clear()

    assert client.get("/auth/session").status_code == 200

    get_settings.cache_clear()


def test_demo_mode_is_off_by_default(client: TestClient, behind_access: None) -> None:
    """The one branch that serves anybody without a check, and it must stay unreachable.

    Asserted from the outside: with Access configured and no assertion supplied, a
    `demo_mode` that had somehow become true would answer 200.
    """
    assert get_settings().demo_mode is False
    assert client.get("/auth/session").status_code == 401
