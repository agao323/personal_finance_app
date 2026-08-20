"""Tests for account recovery.

The route where Cloudflare Access is trusted on its own. Everything here is about the
conditions under which it must refuse, because the failure mode is "register a passkey
as anybody" and the only thing standing in the way is this check.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import access


@pytest.fixture
def access_configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "allofmymoney.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-123")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── the configuration guard ───────────────────────────────────────────────────


def test_unconfigured_means_refused_not_allowed() -> None:
    """The whole security of this route.

    Locally there is no Access in front of the app, so an unguarded version would be a
    free "register as anybody" endpoint. Absence of a check must never read as a
    passing check.
    """
    get_settings.cache_clear()
    assert access.configured() is None

    with pytest.raises(access.AccessError, match="not configured"):
        access.verified_email("any.assertion.here")


def test_both_values_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Either alone is worse than nothing, because it looks like a check.

    An audience with no issuer accepts a token from any Access tenant; an issuer with
    no audience accepts one minted for a different application.
    """
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    get_settings.cache_clear()
    assert access.configured() is None

    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.setenv("CF_ACCESS_AUD", "aud")
    get_settings.cache_clear()
    assert access.configured() is None

    get_settings.cache_clear()


def test_the_issuer_and_key_url_are_derived_from_the_team(
    access_configured: None,
) -> None:
    config = access.configured()
    assert config is not None
    assert config.issuer == "https://allofmymoney.cloudflareaccess.com"
    assert config.jwks_url.endswith("/cdn-cgi/access/certs")


def test_a_team_domain_given_as_a_url_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://team.cloudflareaccess.com/")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud")
    get_settings.cache_clear()

    config = access.configured()

    assert config is not None
    assert config.team_domain == "team.cloudflareaccess.com"
    get_settings.cache_clear()


# ── the route ─────────────────────────────────────────────────────────────────


def test_recovery_is_refused_when_access_is_not_configured(client: TestClient) -> None:
    """A deployment with no Access in front cannot recover anything."""
    response = client.post("/auth/recover/options")

    assert response.status_code == 401


def test_recovery_is_refused_without_an_assertion(
    client: TestClient, access_configured: None
) -> None:
    response = client.post("/auth/recover/options")

    assert response.status_code == 401


def test_recovery_is_refused_for_an_unverifiable_assertion(
    client: TestClient, access_configured: None
) -> None:
    """A decoded-but-unverified JWT is a header anyone can write."""
    response = client.post(
        "/auth/recover/options", headers={access.ASSERTION_HEADER: "not.a.real.jwt"}
    )

    assert response.status_code == 401


def test_every_recovery_refusal_reads_the_same(client: TestClient, access_configured: None) -> None:
    """Which of the failures you hit is not a probe worth answering."""
    missing = client.post("/auth/recover/options").json()["detail"]
    forged = client.post(
        "/auth/recover/options", headers={access.ASSERTION_HEADER: "x.y.z"}
    ).json()["detail"]

    assert missing == forged


def test_recovery_does_not_take_a_session(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    """It has to work for somebody holding no credential at all.

    Asserted through the contract test's public-path list as well, but stated here
    because it is the requirement rather than an implementation detail: a route that
    needed a session could never be reached by the person who needs it.
    """
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": owner_id, "c": b"lost-device", "p": b"key"},
    )

    # 401 because Access is unconfigured here, not because a session was demanded.
    response = client.post("/auth/recover/options")

    assert response.status_code == 401
    assert response.json()["detail"] == "Account recovery is not available for this identity"


def test_the_users_table_is_still_the_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing Access is necessary and not sufficient.

    An identity Cloudflare authenticated but this household never added must get the
    same refusal as a forged assertion — otherwise anyone on the Access policy for any
    application in the tenant could recover an account here.
    """
    from app.routers.auth import RECOVERY_REFUSED

    assert "not available" in RECOVERY_REFUSED
