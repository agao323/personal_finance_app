"""Contract tests.

The freeze that makes Wave 2's three lanes safe. These assert three things:

1. Every declared route exists and answers 501 until its lane implements it.
2. The route inventory in ARCHITECTURE.md matches the running app exactly.
3. Money crosses the wire as integer cents, everywhere, with no exceptions.

A stale inventory is worse than none, because it gets trusted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import API_ROOT

DOCS = API_ROOT.parent / "docs" / "ARCHITECTURE.md"

#: Routes that are no longer stubs.
#:
#: This is a ratchet: implementing a route makes `test_every_stub_returns_501` fail
#: until the path is listed here, so each ticket has to declare what it made live
#: rather than quietly changing the surface. Removing a path from this set is how you
#: would notice a route regressing back to 501.
LIVE_PATHS = {
    "/health",  # 003
    "/ready",  # 003
    "/net-worth",  # 014
    "/net-worth/series",  # 014
    "/spend",  # 015
    "/runway",  # 016
    "/export",  # 017
    "/accounts",  # 019
    "/accounts/{account_id}",  # 019
    "/accounts/{account_id}/history",  # 019
    "/accounts/{account_id}/balances",  # 019
    "/accounts/{account_id}/stakes",  # 019
    "/rules",  # 022
    "/rules/{rule_id}",  # 022
    "/rules/apply",  # 022
    "/rules/preview",  # 033
    "/import/csv/preview",  # 020
    "/import/csv/commit",  # 021
    "/transactions",  # 023
    "/transactions/{transaction_id}",  # 023
    "/transactions/bulk-categorise",  # 023
    "/transactions/bulk-transfer",  # 030
    "/categories",  # 030
    "/auth/register/options",  # 034
    "/auth/register/verify",  # 034
    "/auth/login/options",  # 034
    "/auth/login/verify",  # 034
    "/auth/session",  # 034
    "/auth/logout",  # 034
    "/auth/credentials",  # 041
    "/auth/credentials/{credential_id}",  # 041
    "/members",  # 043
    "/members/{member_id}",  # 043
    "/members/{member_id}/invitation",  # 043
    "/auth/invitation/redeem/options",  # 043
    "/auth/invitation/redeem/verify",  # 043
}


def _openapi() -> dict[str, Any]:
    schema: dict[str, Any] = app.openapi()
    return schema


def _documented_paths() -> set[str]:
    """Parse the endpoint table out of ARCHITECTURE.md."""
    text = DOCS.read_text(encoding="utf-8")
    section = text[text.index("## Endpoints") : text.index("## Account sources")]
    return set(re.findall(r"\|\s*`(/[^`]*)`\s*\|", section))


def _declared_paths() -> set[str]:
    return set(_openapi()["paths"])


# ── inventory ─────────────────────────────────────────────────────────────────


def test_documented_inventory_matches_the_app() -> None:
    documented = _documented_paths()
    declared = _declared_paths()

    assert documented == declared, (
        f"undocumented routes: {sorted(declared - documented)}; "
        f"documented but missing: {sorted(documented - declared)}"
    )


def test_every_documented_path_names_the_ticket_that_lands_it() -> None:
    text = DOCS.read_text(encoding="utf-8")
    section = text[text.index("## Endpoints") : text.index("## Account sources")]
    rows = [ln for ln in section.splitlines() if ln.startswith("| ") and "`/" in ln]

    assert rows, "endpoint table not found"
    for row in rows:
        assert re.search(r"\|\s*\d{3}\s*\|?\s*$", row), f"no ticket number: {row}"


# ── stubs ─────────────────────────────────────────────────────────────────────


def _stub_operations() -> list[tuple[str, str]]:
    operations = []
    for path, methods in _openapi()["paths"].items():
        if path in LIVE_PATHS:
            continue
        for method in methods:
            operations.append((method.upper(), path))
    return sorted(operations)


def test_every_operation_is_either_live_or_stubbed() -> None:
    """Guards the parametrisation below from silently collapsing to nothing.

    Asserting the partition rather than a count: a fixed threshold needed revising
    every time a ticket landed, which trains people to edit the guard instead of
    reading it.
    """
    declared = {
        (method.upper(), path)
        for path, methods in _openapi()["paths"].items()
        for method in methods
    }
    live = {(m, p) for m, p in declared if p in LIVE_PATHS}
    stubbed = set(_stub_operations())

    assert live | stubbed == declared
    assert not (live & stubbed)


#: Minimal valid bodies for routes that require one.
#:
#: FastAPI validates before dispatch, so a route with a required body answers 422 for
#: an invalid one and only reaches the 501 stub with a valid one. Writing these out
#: doubles as proof that the request schemas accept sensible input — a schema nothing
#: can satisfy would otherwise sit undetected until a lane tried to use it.
VALID_BODIES: dict[tuple[str, str], dict[str, Any]] = {}

#: Multipart upload rather than JSON; covered separately below.
MULTIPART: set[tuple[str, str]] = set()


@pytest.mark.parametrize(("method", "path"), _stub_operations())
def test_every_stub_returns_501(client: TestClient, method: str, path: str) -> None:
    """A declared-but-unimplemented route must say so, not 404 or 500.

    501 is what tells a frontend lane "this shape is final, the data is not here yet".
    A 404 would be indistinguishable from a typo in the URL.
    """
    if (method, path) in MULTIPART:
        pytest.skip("covered by test_multipart_stub_returns_501")

    concrete = (
        path.replace("{account_id}", "1").replace("{rule_id}", "1").replace("{transaction_id}", "1")
    )
    body = VALID_BODIES.get((method, path))
    response = client.request(method, concrete, json=body)

    assert response.status_code == 501, (
        f"{method} {path} returned {response.status_code}: {response.text[:200]}"
    )
    assert "ticket" in response.json()["detail"].lower()


def test_every_body_route_has_a_valid_body_fixture() -> None:
    """Stops the map above from silently falling out of step with the routes.

    Reads `requestBody` from the spec rather than assuming every POST takes one —
    /auth/*/options generate their payload server-side and accept nothing.
    """
    body_routes = {
        (method.upper(), path)
        for path, methods in _openapi()["paths"].items()
        for method, operation in methods.items()
        if operation.get("requestBody") and path not in LIVE_PATHS
    }
    missing = body_routes - set(VALID_BODIES) - MULTIPART
    assert not missing, f"no valid-body fixture for: {sorted(missing)}"

    unused = set(VALID_BODIES) - body_routes
    assert not unused, f"fixture for a route that takes no body: {sorted(unused)}"


def test_live_routes_are_not_stubbed(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


# ── money ─────────────────────────────────────────────────────────────────────


def _schema_properties() -> list[tuple[str, str, dict[str, Any]]]:
    components = _openapi().get("components", {}).get("schemas", {})
    return [
        (name, prop, spec)
        for name, schema in components.items()
        for prop, spec in schema.get("properties", {}).items()
    ]


def test_percentages_are_integer_basis_points() -> None:
    """Same reasoning as cents: 33.33 as a double is 33.329999999999998."""
    bps = [(n, p, s) for n, p, s in _schema_properties() if p.endswith("_bps")]
    assert bps, "no basis-point fields found"

    for name, prop, spec in bps:
        types = {spec.get("type")} | {v.get("type") for v in spec.get("anyOf", [])}
        assert "integer" in types, f"{name}.{prop} is {types}, not integer"


def test_money_fields_are_integer_cents() -> None:
    """Every `*_cents` field is an integer on the wire.

    2dp storage round-trips exactly through cents, so no scale field is needed, and an
    integer cannot pick up the representation error that makes 0.1 + 0.2 wrong.
    """
    money = [(n, p, s) for n, p, s in _schema_properties() if p.endswith("_cents")]
    assert money, "no money fields found — the contract cannot be right"

    for name, prop, spec in money:
        types = {spec.get("type")} | {variant.get("type") for variant in spec.get("anyOf", [])}
        assert "integer" in types, f"{name}.{prop} is {types}, not integer"
        assert "number" not in types, f"{name}.{prop} allows a float"


def test_no_schema_field_is_a_bare_float() -> None:
    """The one exception is months_of_runway: a ratio for display, never multiplied
    by a balance, and rounding it costs nothing."""
    allowed = {("BurnWindow", "months_of_runway")}

    for name, prop, spec in _schema_properties():
        types = {spec.get("type")} | {v.get("type") for v in spec.get("anyOf", [])}
        if "number" in types and (name, prop) not in allowed:
            pytest.fail(f"{name}.{prop} is a float; money must be integer cents")


def test_error_shape_is_defined_once() -> None:
    """One error model, so the frontend writes one handler rather than twenty."""
    schemas = _openapi()["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert set(schemas["ErrorResponse"]["properties"]) == {"detail", "errors"}


#: Routes that must stay reachable without a session.
#:
#: `/health` and `/ready` because a health check that needs a session cannot report
#: that the app is unhealthy, and the auth ceremonies because requiring a session to
#: get one is a closed loop.
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/auth/login/options",
    "/auth/login/verify",
    "/auth/register/options",
    "/auth/register/verify",
    "/auth/logout",
    # Redeeming an invitation cannot require a session: the whole point is that the
    # invited person does not have one yet. The token is the credential, it is
    # single-use and expiring, and on the real deployment Cloudflare Access has
    # already refused anyone outside the household before this route is reached.
    "/auth/invitation/redeem/options",
    "/auth/invitation/redeem/verify",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


def _api_routes() -> list[Any]:
    """Every APIRoute in the app, including inside included routers.

    This FastAPI version keeps an included router nested in `app.routes` rather than
    flattening its routes into it, so a non-recursive walk sees only the two routes
    declared on `app` itself — and an "every route is authenticated" assertion over
    that set passes while checking nothing. Worth stating because the vacuous version
    looked identical and green.
    """
    from fastapi.routing import APIRoute

    found: list[Any] = []

    def walk(routes: Any) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                found.append(route)
            elif hasattr(route, "original_router"):
                # `include_router` wraps the router rather than copying its routes in.
                walk(route.original_router.routes)
            elif hasattr(route, "routes"):
                walk(route.routes)

    walk(app.routes)
    return found


def test_the_route_walk_finds_the_whole_surface() -> None:
    """Guards the two tests below from silently checking nothing.

    Both assert a property over "every route"; if the walk returns an empty or tiny
    set they pass regardless. The count is deliberately a floor, not an equality —
    this is a tripwire, not a second inventory.
    """
    assert len(_api_routes()) >= 25


def _depends_on_current_user(dependant: Any) -> bool:
    from app.deps import current_user

    if dependant.call is current_user:
        return True
    return any(_depends_on_current_user(child) for child in dependant.dependencies)


def test_every_non_public_route_requires_authentication() -> None:
    """The property ticket 012 froze, and the one worth actually guarding.

    Wave 2 wrote `user: CurrentUser` on every route that touches household data while
    authentication was a stand-in, and ticket 034 replaced the implementation without
    editing any of them. What protects that is not `current_user`'s parameter list —
    routes never call it directly — it is that the dependency is still *on* them.

    An earlier version of this test asserted the parameter names, which broke the
    moment the real implementation needed the request to read a cookie: it was
    guarding the shape of the plumbing rather than the guarantee.
    """
    unguarded = [
        f"{sorted(route.methods)[0]} {route.path}"
        for route in _api_routes()
        if route.path not in PUBLIC_PATHS and not _depends_on_current_user(route.dependant)
    ]

    assert not unguarded, f"routes with no authentication: {sorted(unguarded)}"


def test_the_public_routes_really_are_public() -> None:
    """Stops the list above from quietly becoming a way to exempt a real route."""
    declared = {route.path for route in _api_routes()}
    stale = {path for path in PUBLIC_PATHS if path.startswith("/auth")} - declared

    assert not stale, f"public exemption for a route that does not exist: {sorted(stale)}"


def test_openapi_exports_without_a_database(tmp_path: Path) -> None:
    """The contract pipeline must not need a running database.

    CI regenerates types with nothing up; if this regresses, `make types-check` starts
    failing for reasons unrelated to the contract.
    """
    from scripts.export_openapi import export

    output = export(tmp_path / "openapi.json")
    assert output.exists()
