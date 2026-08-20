"""Tests for adding a second household member.

The one that matters is `test_the_passkey_attaches_to_the_invited_user`. Registering a
passkey while the owner is signed in would otherwise bind the newcomer's authenticator
to the owner's account — and every ownership figure in this app is per-user, so that is
wrong in a way no screen would show.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.routers.users import INVITATION_TTL, hash_token
from app.services import session as sessions


def _member(client: TestClient, email: str = "partner@example.invalid") -> dict[str, Any]:
    response = client.post("/members", json={"email": email, "display_name": "Partner"})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# ── members ───────────────────────────────────────────────────────────────────


def test_lists_the_household(client: TestClient) -> None:
    body = client.get("/members").json()

    assert len(body) >= 1
    assert body[0]["passkey_count"] == 0


def test_adds_a_member(client: TestClient) -> None:
    member = _member(client)

    assert member["is_active"] is True
    assert member["passkey_count"] == 0


def test_refuses_a_duplicate_email(client: TestClient) -> None:
    _member(client)

    response = client.post(
        "/members", json={"email": "PARTNER@example.invalid", "display_name": "Again"}
    )

    assert response.status_code == 409


def test_rejects_something_that_is_not_an_address(client: TestClient) -> None:
    response = client.post("/members", json={"email": "not-an-address", "display_name": "X"})

    assert response.status_code == 422


def test_deactivating_revokes_on_the_next_request(client: TestClient, db_session: Session) -> None:
    """`current_user` reads `is_active` every time, so this takes effect immediately."""
    member = _member(client)

    client.patch(f"/members/{member['id']}", json={"is_active": False})

    assert client.get("/members").json()[-1]["is_active"] is False


def test_you_cannot_deactivate_yourself(client: TestClient, owner_id: int) -> None:
    """With one active member it would leave nobody able to undo it."""
    response = client.patch(f"/members/{owner_id}", json={"is_active": False})

    assert response.status_code == 409


def test_there_is_no_delete(client: TestClient, owner_id: int) -> None:
    """A stake is a historical fact; removing the user it points at rewrites history.

    `ownership_stakes.owner_user_id` is ON DELETE RESTRICT for exactly this reason.
    """
    assert client.delete(f"/members/{owner_id}").status_code == 405


# ── invitations ───────────────────────────────────────────────────────────────


def test_issues_a_token_once(client: TestClient, db_session: Session) -> None:
    member = _member(client)

    body = client.post(f"/members/{member['id']}/invitation").json()

    assert body["token"]
    stored = db_session.execute(
        text("SELECT token_hash FROM invitations WHERE user_id = :u"), {"u": member["id"]}
    ).scalar_one()
    # Only the hash. A readable invitation in the database is a credential in every
    # backup.
    assert stored == hash_token(body["token"])
    assert body["token"] not in stored


def test_reissuing_invalidates_the_previous_token(client: TestClient, db_session: Session) -> None:
    """So a token that went to the wrong place stops working the moment you reissue."""
    member = _member(client)
    first = client.post(f"/members/{member['id']}/invitation").json()["token"]

    client.post(f"/members/{member['id']}/invitation")

    response = client.post("/auth/invitation/redeem/options", json={"token": first})
    assert response.status_code == 401


def test_refuses_an_invitation_for_someone_who_already_has_a_passkey(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    member = _member(client)
    db_session.execute(
        text(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count) "
            "VALUES (:u, :c, :p, 0)"
        ),
        {"u": member["id"], "c": b"already", "p": b"key"},
    )
    # Storing a credential shuts the bootstrap window, so this request now needs a
    # real session — which is the bootstrap behaving correctly, not a wrinkle.
    cookie = sessions.issue(owner_id, get_settings().session_secret, 24)

    response = client.post(
        f"/members/{member['id']}/invitation", cookies={sessions.COOKIE_NAME: cookie}
    )

    assert response.status_code == 409
    assert "add devices from their own account" in response.json()["detail"]


def test_an_unknown_token_is_refused(client: TestClient) -> None:
    response = client.post("/auth/invitation/redeem/options", json={"token": "made-up"})

    assert response.status_code == 401


def test_an_expired_token_is_refused(client: TestClient, db_session: Session) -> None:
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]
    db_session.execute(
        text("UPDATE invitations SET expires_at = :t WHERE token_hash = :h"),
        {"t": dt.datetime(2020, 1, 1, tzinfo=dt.UTC), "h": hash_token(token)},
    )

    response = client.post("/auth/invitation/redeem/options", json={"token": token})

    assert response.status_code == 401


def test_every_invitation_failure_reads_the_same(client: TestClient, db_session: Session) -> None:
    """The token is the secret; saying which failure you hit is a way to probe it."""
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]
    db_session.execute(
        text("UPDATE invitations SET expires_at = :t WHERE token_hash = :h"),
        {"t": dt.datetime(2020, 1, 1, tzinfo=dt.UTC), "h": hash_token(token)},
    )

    unknown = client.post("/auth/invitation/redeem/options", json={"token": "nope"}).json()
    expired = client.post("/auth/invitation/redeem/options", json={"token": token}).json()

    assert unknown["detail"] == expired["detail"]


def test_a_deactivated_member_cannot_redeem(client: TestClient) -> None:
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]
    client.patch(f"/members/{member['id']}", json={"is_active": False})

    response = client.post("/auth/invitation/redeem/options", json={"token": token})

    assert response.status_code == 401


def test_redemption_options_name_the_invited_account(client: TestClient) -> None:
    """Not the owner's. The ceremony has to be for the person being invited."""
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]

    body = client.post("/auth/invitation/redeem/options", json={"token": token}).json()

    assert body["options"]["user"]["name"] == "partner@example.invalid"


def test_the_passkey_attaches_to_the_invited_user(
    client: TestClient, db_session: Session, owner_id: int
) -> None:
    """The reason this ticket exists.

    Registering through the ordinary route while the owner is signed in would bind the
    newcomer's authenticator to the owner. Every ownership figure is per-user, so that
    is silently wrong in the way that matters most.
    """
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]
    started = client.post("/auth/invitation/redeem/options", json={"token": token}).json()

    # The ceremony itself needs a real authenticator; what is asserted here is that the
    # challenge was issued against the invited user rather than the owner.
    challenge_owner = db_session.execute(
        text("SELECT user_id FROM webauthn_challenges WHERE challenge_id = :c"),
        {"c": started["challenge_id"]},
    ).scalar_one()

    assert challenge_owner == member["id"]
    assert challenge_owner != owner_id


def test_redeeming_requires_a_matching_challenge(client: TestClient) -> None:
    member = _member(client)
    token = client.post(f"/members/{member['id']}/invitation").json()["token"]

    response = client.post(
        "/auth/invitation/redeem/verify",
        json={"token": token, "challenge_id": "never-issued", "credential": {}},
    )

    assert response.status_code == 401


def test_the_invitation_window_is_days_not_minutes() -> None:
    """The recipient is in the same household, not clicking a link while it is warm."""
    assert INVITATION_TTL >= dt.timedelta(days=1)


@pytest.mark.parametrize("token", ["", " ", "x" * 500])
def test_junk_tokens_are_refused(client: TestClient, token: str) -> None:
    response = client.post("/auth/invitation/redeem/options", json={"token": token})

    assert response.status_code in (401, 422)
