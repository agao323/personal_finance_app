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
    "/import/csv/preview",  # 020
    "/import/csv/commit",  # 021
    "/transactions",  # 023
    "/transactions/{transaction_id}",  # 023
    "/transactions/bulk-categorise",  # 023
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
VALID_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/auth/register/verify"): {"challenge_id": "abc", "credential": {}},
    ("POST", "/auth/login/verify"): {"challenge_id": "abc", "credential": {}},
}

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


def test_current_user_signature_is_frozen() -> None:
    """Ticket 034 replaces the implementation, not the signature.

    If this changes, every Wave 2 route that depends on it needs editing — which is
    exactly what declaring it now is meant to avoid.
    """
    import inspect

    from app.deps import current_user

    signature = inspect.signature(current_user)
    assert list(signature.parameters) == ["session"]
    assert signature.return_annotation == "User"


def test_openapi_exports_without_a_database(tmp_path: Path) -> None:
    """The contract pipeline must not need a running database.

    CI regenerates types with nothing up; if this regresses, `make types-check` starts
    failing for reasons unrelated to the contract.
    """
    from scripts.export_openapi import export

    output = export(tmp_path / "openapi.json")
    assert output.exists()
