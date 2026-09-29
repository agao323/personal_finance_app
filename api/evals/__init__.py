"""The advisor's evals: a synthetic world, golden questions, and answers computed from the app.

docs/ADVISOR.md#evals. Everything here runs on generated data — the demo's seed at a pinned
date plus `overlay.py` — and never against a database whose `data_marker` says it is real.

- `overlay.py` plants what the demo does not need: subscriptions, a spending spike, an
  unmarked transfer, an urgent perk, a stale balance, and the injection corpus.
- `facts.py` computes every expected figure through the tools the model calls.
- `cases/*.yaml` are the golden questions; `injection.yaml` is the planted corpus.
- `expected.json` is `facts.py`'s output, committed and checked for drift in CI.

CI runs everything here that needs no model. `make eval` (ticket 102) runs the rest.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: The pinned date the fixture world is built for. A Tuesday in the third quarter, so
#: "this quarter against last quarter" compares a partial quarter like-for-like.
EVAL_TODAY = dt.date(2026, 8, 18)
EVAL_SEED = 20260818

ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
CORPUS_PATH = ROOT / "injection.yaml"
EXPECTED_PATH = ROOT / "expected.json"
#: The eval world's returns table: synthetic, like everything else in it (ticket 118).
RETURNS_PATH = ROOT / "returns_synthetic.csv"

CATEGORIES = (
    "lookup",
    "comparison",
    "trend",
    "multi_hop",
    "scope",
    "gap",
    "write_intent",
    "injection",
    "goal_aware",
    "fire",
    "review",
)


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    scope: str
    question: str
    facts: list[str] = field(default_factory=list)
    tools_any: list[str] = field(default_factory=list)
    tools_none: list[str] = field(default_factory=list)
    #: Every one of these must be called: a review's fixed lookups (plan 119).
    tools_all: list[str] = field(default_factory=list)
    max_tool_calls: int | None = None
    expect_limitation: str | None = None
    canaries: list[str] = field(default_factory=list)
    expect_screen: str | None = None
    #: A review of the month before `EVAL_TODAY`, asked with the review's fixed prompt.
    review: bool = False
    #: Bold section headings the answer must contain, in any order.
    expect_sections: list[str] = field(default_factory=list)
    #: A case whose tools land in a later ticket: listed now, run once that ticket ships.
    pending: str | None = None


@dataclass(frozen=True)
class Planted:
    id: str
    canary: str
    field: str
    text: str
    #: Whether the sanitiser should keep the canary from the model: withheld as
    #: instruction-like, or removed with the link it was in. The subtle ones are false —
    #: they are there for the model, not the sanitiser.
    withheld: bool
    kind: str


def load_cases() -> list[Case]:
    cases: list[Case] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            cases.append(Case(**raw))
    return cases


def load_corpus() -> list[Planted]:
    raw = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))
    return [Planted(**entry) for entry in raw]


def load_expected() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    return data


@contextmanager
def synthetic_returns() -> Iterator[None]:
    """Projections in the eval world run on its synthetic returns table (ticket 118). Production
    refuses a synthetic table; the eval world is synthetic end to end, so it opts in here."""
    from app.services.analysis import projections

    with projections.returns_override(projections.load_returns(RETURNS_PATH)):
        yield
