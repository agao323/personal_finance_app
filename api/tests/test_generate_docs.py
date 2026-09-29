"""docs/generated/ is derived from the code and never hand-kept.

The first test *is* the drift check — it is how `make test` enforces it, alongside the
explicit `make docs-check` in CI. The rest prove the check can fail: a drift check that
never fires looks exactly like one that is broken.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Numeric, Table

from app.db import Base
from app.main import app
from scripts.generate_docs import (
    DEFAULT_OUT,
    ENDPOINTS_FILE,
    FIX,
    SCHEMA_FILE,
    check,
    render_all,
    render_api_endpoints,
    render_db_schema,
    write,
)


def test_the_committed_generated_docs_are_current() -> None:
    problems = check(DEFAULT_OUT)
    assert not problems, "\n".join(problems) + "\n\n" + FIX


# ── the check can fail ────────────────────────────────────────────────────────


def test_a_fresh_write_passes(tmp_path: Path) -> None:
    rendered = render_all()
    write(tmp_path, rendered)

    assert check(tmp_path, rendered) == []


def test_a_hand_edit_fails_and_shows_the_diff(tmp_path: Path) -> None:
    rendered = render_all()
    write(tmp_path, rendered)
    edited = tmp_path / SCHEMA_FILE
    edited.write_text(
        edited.read_text(encoding="utf-8").replace("NUMERIC(19, 2)", "FLOAT", 1), encoding="utf-8"
    )

    problems = check(tmp_path, rendered)

    assert len(problems) == 1
    assert SCHEMA_FILE in problems[0]
    assert "FLOAT" in problems[0]


def test_a_missing_file_fails(tmp_path: Path) -> None:
    rendered = render_all()
    write(tmp_path, rendered)
    (tmp_path / ENDPOINTS_FILE).unlink()

    assert check(tmp_path, rendered) == [f"docs/generated/{ENDPOINTS_FILE} is missing."]


def test_the_failure_says_how_to_fix_it() -> None:
    assert "make docs" in FIX
    assert "never hand-edited" in FIX


# ── the output covers everything ──────────────────────────────────────────────


def test_the_schema_doc_names_every_table() -> None:
    text = render_db_schema()

    for name in Base.metadata.tables:
        assert f"\n## {name}\n" in text, f"{name} missing from {SCHEMA_FILE}"


def test_the_endpoint_doc_names_every_operation() -> None:
    openapi = app.openapi()
    text = render_api_endpoints(openapi)

    for path, methods in openapi["paths"].items():
        for method in methods:
            assert f"| {method.upper()} | `{path}` |" in text, f"{method} {path} missing"


def test_the_schema_doc_reads_the_metadata_it_is_given() -> None:
    """A model change shows up — the generator reads metadata, not a snapshot of it."""
    metadata = MetaData()
    Table(
        "widgets",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("price", Numeric(19, 2), nullable=False),
    )

    text = render_db_schema(metadata)

    assert "## widgets" in text
    assert "| `price` | NUMERIC(19, 2) | no |" in text


def test_rendering_is_deterministic() -> None:
    assert render_all() == render_all()
