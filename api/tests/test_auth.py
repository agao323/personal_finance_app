"""Tests for passkey authentication.

The ceremonies themselves need a real authenticator, so the parts that can be asserted
without one are: the pure decisions (sign counts, session cookies, RP configuration),
the allowlist behaviour, and that a failed ceremony is refused *identically* however it
failed.

The full ceremony is covered end to end by ticket 038's Playwright run against a
virtual authenticator, which is the only way to exercise it honestly.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import session as sessions
from app.services import webauthn

SECRET = "test-secret"


# ── sign counts ───────────────────────────────────────────────────────────────


def test_a_counter_that_advances_is_accepted() -> None:
    assert webauthn.sign_count_is_valid(4, 5) is True


def test_a_counter_that_goes_backwards_is_rejected() -> None:
    """A clone, or a replay. Both are refused."""
    assert webauthn.sign_count_is_valid(9, 4) is False


def test_a_repeated_counter_is_rejected() -> None:
    """Not advancing is the signal — equal is not "greater than"."""
    assert webauthn.sign_count_is_valid(5, 5) is False


def test_an_authenticator_that_never_counts_is_allowed() -> None:
    """Reporting a constant zero is permitted by the spec.

    Treating it as an attack would lock out a whole class of hardware for no gain —
    it is the absence of a signal, not a bad one.
    """
    assert webauthn.sign_count_is_valid(0, 0) is True


# ── session cookies ───────────────────────────────────────────────────────────


def test_a_session_round_trips() -> None:
    assert sessions.read(sessions.issue(7, SECRET, 24), SECRET) == 7


def test_a_tampered_payload_is_rejected() -> None:
    """Without the signature, "user id 1" is a value anyone can type."""
    cookie = sessions.issue(7, SECRET, 24)
    body, _, signature = cookie.partition(".")

    with pytest.raises(sessions.SessionError):
        sessions.read(f"{body}x.{signature}", SECRET)


def test_a_cookie_signed_with_another_secret_is_rejected() -> None:
    """Which is what makes rotating SESSION_SECRET a global logout."""
    with pytest.raises(sessions.SessionError):
        sessions.read(sessions.issue(7, "old-secret", 24), SECRET)


def test_an_expired_session_is_rejected() -> None:
    issued = sessions.issue(7, SECRET, 1, now=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))

    with pytest.raises(sessions.SessionError):
        sessions.read(issued, SECRET, now=dt.datetime(2026, 1, 1, 2, tzinfo=dt.UTC))


def test_a_malformed_cookie_is_rejected() -> None:
    with pytest.raises(sessions.SessionError):
        sessions.read("not-a-cookie", SECRET)


# ── RP configuration ──────────────────────────────────────────────────────────


def test_rp_id_defaults_to_localhost_for_development() -> None:
    """Browsers special-case localhost as a secure origin, so dev needs no TLS."""
    assert get_settings().rp_id == "localhost"


def test_cookie_security_is_derived_from_the_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two settings that must agree are one setting and a bug waiting to happen."""
    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    get_settings.cache_clear()

    assert get_settings().cookie_secure is True

    get_settings.cache_clear()


def test_the_default_session_secret_is_detectable() -> None:
    """So a deployment can refuse to start on it rather than signing with a known key."""
    assert get_settings().session_secret_is_default is True


# ── challenges ────────────────────────────────────────────────────────────────


def test_a_challenge_is_spent_on_first_use(client: TestClient, db_session: Session) -> None:
    """A challenge that can be answered twice is not a challenge."""
    body = client.post("/auth/login/options").json()
    challenge_id = body["challenge_id"]

    stored = db_session.execute(
        text("SELECT count(*) FROM webauthn_challenges WHERE challenge_id = :c"),
        {"c": challenge_id},
    ).scalar_one()
    assert stored == 1

    # Answering with nonsense still consumes it.
    client.post("/auth/login/verify", json={"challenge_id": challenge_id, "credential": {}})

    remaining = db_session.execute(
        text("SELECT count(*) FROM webauthn_challenges WHERE challenge_id = :c"),
        {"c": challenge_id},
    ).scalar_one()
    assert remaining == 0


def test_an_unknown_challenge_is_refused(client: TestClient) -> None:
    response = client.post(
        "/auth/login/verify", json={"challenge_id": "never-issued", "credential": {}}
    )

    assert response.status_code == 401


def test_a_registration_challenge_cannot_answer_a_login(client: TestClient) -> None:
    """A confused-deputy shape worth refusing outright."""
    challenge_id = client.post("/auth/register/options").json()["challenge_id"]

    response = client.post(
        "/auth/login/verify", json={"challenge_id": challenge_id, "credential": {}}
    )

    assert response.status_code == 401


def test_an_expired_challenge_is_refused(client: TestClient, db_session: Session) -> None:
    challenge_id = client.post("/auth/login/options").json()["challenge_id"]
    db_session.execute(
        text("UPDATE webauthn_challenges SET expires_at = :t WHERE challenge_id = :c"),
        {"t": dt.datetime(2020, 1, 1, tzinfo=dt.UTC), "c": challenge_id},
    )

    response = client.post(
        "/auth/login/verify", json={"challenge_id": challenge_id, "credential": {}}
    )

    assert response.status_code == 401


def test_every_refusal_reads_the_same(client: TestClient) -> None:
    """Distinguishing failures tells an attacker which addresses are in the household."""
    unknown = client.post(
        "/auth/login/verify", json={"challenge_id": "nope", "credential": {}}
    ).json()["detail"]
    challenge_id = client.post("/auth/login/options").json()["challenge_id"]
    bad_credential = client.post(
        "/auth/login/verify", json={"challenge_id": challenge_id, "credential": {}}
    ).json()["detail"]

    assert unknown == bad_credential


# ── the allowlist and the bootstrap ───────────────────────────────────────────


def test_registration_options_name_the_configured_relying_party(client: TestClient) -> None:
    body = client.post("/auth/register/options").json()

    assert body["options"]["rp"]["id"] == "localhost"


def test_the_bootstrap_window_is_open_before_any_passkey_exists(client: TestClient) -> None:
    """Registering needs a session; getting a session needs a passkey.

    Something has to open the door once, and while `credentials` is empty there is no
    passkey anyone *could* present.
    """
    assert client.get("/auth/session").status_code == 200


def test_the_bootstrap_window_closes_once_a_passkey_is_registered(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": owner_id, "c": b"cred-1", "p": b"key-1"},
    )

    response = client.get("/auth/session")

    assert response.status_code == 401


def test_a_valid_cookie_authenticates(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": owner_id, "c": b"cred-2", "p": b"key-2"},
    )
    cookie = sessions.issue(owner_id, get_settings().session_secret, 24)

    response = client.get("/auth/session", cookies={sessions.COOKIE_NAME: cookie})

    assert response.status_code == 200
    assert response.json()["user_id"] == owner_id


def test_deactivating_a_user_revokes_their_session_immediately(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    """The `users` table is the allowlist, read on every request.

    Trusting what was true when the cookie was issued would leave a removed household
    member signed in until it expired.
    """
    cookie = sessions.issue(owner_id, get_settings().session_secret, 24)
    db_session.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": owner_id})

    response = client.get("/auth/session", cookies={sessions.COOKIE_NAME: cookie})

    assert response.status_code == 401


def test_an_expired_cookie_does_not_fall_back_to_the_bootstrap(
    client: TestClient, owner_id: int
) -> None:
    """Otherwise an expired session silently downgrades to unauthenticated access."""
    expired = sessions.issue(
        owner_id, get_settings().session_secret, 1, now=dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    )

    response = client.get("/auth/session", cookies={sessions.COOKIE_NAME: expired})

    assert response.status_code == 401


def test_a_forged_cookie_is_refused(client: TestClient, owner_id: int) -> None:
    forged = sessions.issue(owner_id, "attacker-secret", 24)

    assert client.get("/auth/session", cookies={sessions.COOKIE_NAME: forged}).status_code == 401


def test_protected_routes_refuse_an_unauthenticated_request(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    """The dependency guards every route that touches household data, not just /auth."""
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": owner_id, "c": b"cred-3", "p": b"key-3"},
    )

    for path in ("/net-worth", "/accounts", "/transactions", "/spend", "/runway", "/export"):
        assert client.get(path).status_code == 401, path


def test_health_and_readiness_stay_public(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    """A health check that needs a session cannot report the app is unhealthy."""
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": owner_id, "c": b"cred-4", "p": b"key-4"},
    )

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_logout_clears_the_cookie(client: TestClient) -> None:
    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert sessions.COOKIE_NAME in response.headers.get("set-cookie", "")
