"""Unit tests for the OpenAPI export script.

These guard the contract pipeline itself. If the export silently stops including a
route or stops being deterministic, `make types` produces a file that looks fine and
is wrong — and Wave 2's three parallel lanes are typed against it.
"""

import json
from pathlib import Path

from scripts.export_openapi import build_schema, export, serialise


def test_schema_contains_the_known_routes() -> None:
    schema = build_schema()
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]


def test_schema_describes_the_response_models() -> None:
    schema = build_schema()
    ok = schema["paths"]["/ready"]["get"]["responses"]["200"]
    ref = ok["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ReadyResponse")

    ready = schema["components"]["schemas"]["ReadyResponse"]
    assert set(ready["properties"]) == {"status", "database"}


def test_ready_documents_its_503() -> None:
    """The 503 is part of the contract — a caller has to be able to see it."""
    responses = build_schema()["paths"]["/ready"]["get"]["responses"]
    assert "503" in responses


def test_export_writes_valid_json(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "openapi.json"

    written = export(output)

    assert written == output
    assert json.loads(output.read_text())["paths"]["/health"]


def test_serialisation_is_deterministic() -> None:
    """The drift check diffs regenerated output against a committed file.

    Run-to-run key reordering would produce spurious failures, and a check that cries
    wolf is a check people stop reading.
    """
    assert serialise(build_schema()) == serialise(build_schema())


def test_serialisation_ends_with_a_newline() -> None:
    assert serialise(build_schema()).endswith("\n")
