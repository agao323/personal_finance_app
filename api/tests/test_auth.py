"""What is left of authentication after ticket 047b.

Cloudflare Access authenticates and the `users` table authorises, so the substance of
this area now lives in `test_deps_access_auth.py`. What remains here is the shape of the
surface: which routes need an identity, which deliberately do not, and what `/auth/session`
reports.

Everything that used to be in this file — WebAuthn ceremonies, challenge spending, sign
counters, cookie signing and expiry, the bootstrap window — went with the code it tested.
See docs/adr/0007-drop-passkeys.md.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_session_route_reports_the_signed_in_member(client: TestClient) -> None:
    response = client.get("/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "owner@example.invalid"
    assert body["display_name"]
    assert isinstance(body["user_id"], int)


def test_protected_routes_refuse_an_unauthenticated_request(
    client: TestClient, unauthenticated: None
) -> None:
    """The dependency guards every route that touches household data, not just /auth."""
    for path in ("/net-worth", "/accounts", "/transactions", "/spend", "/runway", "/export"):
        assert client.get(path).status_code == 401, path


def test_health_and_readiness_stay_public(client: TestClient, unauthenticated: None) -> None:
    """A health check that needs an identity cannot report the app is unhealthy.

    This matters more than it did. Fly's prober runs inside the machine and carries no
    Access assertion, so a probe that authenticated would fail on every machine at once
    — which is the failure that took the web app down in ticket 035 and had to be fixed
    a second time in `proxy.ts`.
    """
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_there_is_no_sign_out_route(client: TestClient) -> None:
    """The only session is Cloudflare's, and only Cloudflare can end it.

    Asserted rather than left implicit: a `/auth/logout` that answered 204 while ending
    nothing would be the most misleading possible response.
    """
    assert client.post("/auth/logout").status_code == 404
