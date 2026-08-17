"""Export the FastAPI OpenAPI schema to a file.

Runs without booting a server and without touching the database: ``app.main`` builds
the schema from the Pydantic models alone, and ``app.db`` constructs its engine
lazily. That keeps ``make types`` usable in CI with nothing running.

The Pydantic models are the contract. This script is the only thing that turns them
into something the frontend can consume — see docs/ARCHITECTURE.md#the-api-contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def build_schema() -> dict[str, Any]:
    """Return the OpenAPI schema as FastAPI generates it."""
    # Imported here rather than at module scope so `--help` works even if the
    # application fails to import.
    from app.main import app

    schema: dict[str, Any] = app.openapi()
    return schema


def serialise(schema: dict[str, Any]) -> str:
    """Render the schema deterministically.

    ``sort_keys`` matters: the drift check compares regenerated output against the
    committed file, so any run-to-run key reordering would surface as a spurious
    failure that people learn to ignore.
    """
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def export(output: Path = DEFAULT_OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialise(build_schema()), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"where to write the schema (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    written = export(args.output)
    print(f"wrote {written}")


if __name__ == "__main__":
    main()
