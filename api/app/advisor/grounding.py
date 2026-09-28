"""Every figure in an answer, traced to the lookup that produced it — or marked as not.

docs/ADVISOR.md#grounding, after *Proof-Carrying Numbers* (2025):

1. **References.** The model writes `{{c2.net_worth}}`; this module writes the figure in, in
   the exact form `render.py` gave it, and records it **verified** with its source call and
   path. The model never types a figure it was given, so it cannot mistype one. A reference
   that names nothing stays in the text and is **unverified**.
2. **The backstop.** Money, percentages, months and unit counts the model typed itself are
   matched against this conversation's tool results in canonical forms only — exact, whole
   dollars half-up, one-decimal `k`/`M`, magnitude without sign — and marked **matched**, or
   **unverified** if nothing matches. "About $1,200" for $1,234.56 fails, on purpose.

**What this proves, and what it does not.** It proves where a figure came from. It does not
prove that the sentence around it is true: "spending rose $412 because of dining" passes if
$412 came from a lookup, whether or not dining is why. That is the evals' job (ADR 0011).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.advisor import render
from app.advisor.render import Figure
from app.schemas.advisor import FigureCheck, FigureSource, FigureStatus
from app.schemas.common import ViewScope

#: `{{c2.net_worth}}`, `{{ c4.buckets.3.change }}`.
REFERENCE = re.compile(r"\{\{\s*(c\d+(?:\.\w+)+)\s*\}\}")
#: What a reference can look like before its closing braces have arrived.
_PARTIAL = re.compile(r"\{(?:\{\s*(?:c(?:\d+(?:\.\w*)*)?)?\s*\}?)?")
_MAX_REFERENCE = 120

_MONEY = re.compile(
    r"(?<![\w$])(?P<neg>-)?\$(?P<neg2>-)?"
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d+))?(?P<suffix>[kKM](?![A-Za-z]))?"
)
_PERCENT = re.compile(r"(?<![\w.$,])(?P<neg>-)?(?P<int>\d+)(?:\.(?P<dec>\d+))?\s?%")
_MONTHS = re.compile(r"(?<![\w.$,])(?P<int>\d+)(?:\.(?P<dec>\d+))? months?\b")
_COUNT = re.compile(
    r"(?<![\w.$,/:-])(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?![\w.,/%:$-])\s+(?P<noun>[A-Za-z][\w-]*)"
)
_SCREEN = re.compile(r"\[\[screen:[a-z_]+\]\]")
_MONTH_NAMES = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|"
    "july|august|september|october|november|december"
)
#: A number right after a month name is a day of the month: "Sep 27", "June 30".
_AFTER_MONTH = re.compile(rf"(?i)\b(?:{_MONTH_NAMES})\.?\s+$")
#: A number describing a window rather than a quantity: "the last 3 months", "next 30 days".
_WINDOW = re.compile(
    r"(?i)\b(?:last|past|next|trailing|previous|prior|over|within|every|each|first|final)\s+$"
)
_PERIOD_NOUNS = frozenset(
    {"day", "days", "week", "weeks", "month", "months", "year", "years", "quarter", "quarters"}
)


@dataclass
class Evidence:
    """What this conversation's lookups proved: figures by reference, scopes, and counts."""

    figures: dict[str, Figure] = field(default_factory=dict)
    #: Call id → the view its figures are in, or None for an unscoped call.
    views: dict[str, ViewScope | None] = field(default_factory=dict)
    #: Unit counts: every integer in a result, and every list's length.
    counts: set[int] = field(default_factory=set)

    def add(self, rendering: str) -> None:
        """Take in one tool result as the model saw it. Errors carry nothing and add nothing."""
        try:
            envelope = json.loads(rendering)
        except ValueError:
            return
        if not isinstance(envelope, dict) or "call" not in envelope:
            return
        view = envelope.get("view")
        self.views[str(envelope["call"])] = ViewScope(view) if view else None
        self.figures.update(render.figures_in(rendering))
        _collect_counts(envelope.get("data"), self.counts)

    def add_all(self, renderings: Iterable[str]) -> None:
        for rendering in renderings:
            self.add(rendering)


def _collect_counts(value: Any, counts: set[int]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        counts.add(abs(value))
    elif isinstance(value, list):
        counts.add(len(value))
        for item in value:
            _collect_counts(item, counts)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_counts(item, counts)


def _source(ref: str) -> FigureSource:
    call_id, _, path = ref.partition(".")
    return FigureSource(call_id=call_id, path=path)


# ── references, as the text streams ───────────────────────────────────────────


class StreamResolver:
    """Writes figures in for references as text streams, holding back a partial reference.

    A reference can arrive split across chunks — `{{c2.net` then `_worth}}` — so text from
    a `{` onward is held until it is either a complete reference or clearly not one.
    """

    def __init__(self, evidence: Evidence) -> None:
        self.evidence = evidence
        self._held = ""

    def feed(self, chunk: str) -> str:
        text = self._held + chunk
        self._held = ""
        out: list[str] = []
        while text:
            start = text.find("{")
            if start < 0:
                out.append(text)
                break
            out.append(text[:start])
            text = text[start:]
            end = text.find("}}")
            if end >= 0:
                candidate = text[: end + 2]
                match = REFERENCE.fullmatch(candidate)
                if match:
                    out.append(self._written(match))
                    text = text[end + 2 :]
                    continue
            if end < 0 and len(text) <= _MAX_REFERENCE and _PARTIAL.fullmatch(text):
                self._held = text  # may yet become a reference
                break
            out.append(text[0])
            text = text[1:]
        return "".join(out)

    def flush(self) -> str:
        held, self._held = self._held, ""
        return held

    def _written(self, match: re.Match[str]) -> str:
        figure = render.resolve(match[1], self.evidence.figures)
        return figure.display if figure else match[0]


# ── the final check ───────────────────────────────────────────────────────────


@dataclass
class Checked:
    text: str
    figures: list[FigureCheck]

    @property
    def unverified(self) -> list[str]:
        return [
            self.text[f.start : f.end] for f in self.figures if f.status is FigureStatus.UNVERIFIED
        ]

    def grounded_spans(self) -> list[tuple[int, int]]:
        return [(f.start, f.end) for f in self.figures if f.status is not FigureStatus.UNVERIFIED]


def check(text: str, evidence: Evidence, *, question: str = "") -> Checked:
    """Resolve every reference, then check every figure the model typed itself."""
    out: list[str] = []
    figures: list[FigureCheck] = []
    position = 0
    length = 0
    for match in REFERENCE.finditer(text):
        before = text[position : match.start()]
        out.append(before)
        length += len(before)
        figure = render.resolve(match[1], evidence.figures)
        written = figure.display if figure else match[0]
        if figure:
            figures.append(
                FigureCheck(
                    start=length,
                    end=length + len(written),
                    status=FigureStatus.VERIFIED,
                    source=_source(figure.ref),
                )
            )
        else:
            figures.append(
                FigureCheck(
                    start=length,
                    end=length + len(written),
                    status=FigureStatus.UNVERIFIED,
                    reason=f"No lookup produced {match[1]}.",
                )
            )
        out.append(written)
        length += len(written)
        position = match.end()
    out.append(text[position:])
    resolved = "".join(out)

    taken = [(f.start, f.end) for f in figures]
    taken += [(m.start(), m.end()) for m in _SCREEN.finditer(resolved)]
    asked = set(_numbers_in(question))
    for start, end, kind, match in _typed_figures(resolved, taken):
        if match.group("int").replace(",", "") in asked:
            continue
        found = _match(kind, match, evidence)
        figures.append(
            FigureCheck(
                start=start,
                end=end,
                status=FigureStatus.MATCHED if found is not False else FigureStatus.UNVERIFIED,
                source=_source(found.ref) if isinstance(found, Figure) else None,
                reason=None if found is not False else "Not found in any lookup this conversation.",
            )
        )
    figures.sort(key=lambda f: f.start)
    return Checked(resolved, figures)


def _numbers_in(text: str) -> list[str]:
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)]


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < b and a < end for a, b in spans)


def _typed_figures(
    text: str, taken: list[tuple[int, int]]
) -> list[tuple[int, int, str, re.Match[str]]]:
    found: list[tuple[int, int, str, re.Match[str]]] = []
    for kind, pattern in (("money", _MONEY), ("percent", _PERCENT), ("months", _MONTHS)):
        for match in pattern.finditer(text):
            if _overlaps(match.start(), match.end(), taken):
                continue
            taken = [*taken, (match.start(), match.end())]
            if (
                kind == "months"
                and not match.group("dec")
                and _WINDOW.search(text[: match.start()])
            ):
                continue  # "the last 3 months" is a window, not a figure
            found.append((match.start(), match.end(), kind, match))
    for match in _COUNT.finditer(text):
        start, end = match.start(), match.end("int")
        if _overlaps(start, end, taken) or _ignored_count(text, match):
            continue
        found.append((start, end, "count", match))
    return found


def _ignored_count(text: str, match: re.Match[str]) -> bool:
    """Dates, years, ordinals and windows are not quantities a lookup must prove."""
    number = int(match.group("int").replace(",", ""))
    before = text[: match.start()]
    if "," not in match.group("int") and 1900 <= number <= 2199:
        return True  # a year
    if _AFTER_MONTH.search(before):
        return True  # "Sep 27"
    return bool(_WINDOW.search(before) and match.group("noun").lower() in _PERIOD_NOUNS)


def _amount(match: re.Match[str]) -> tuple[Decimal, int]:
    """The number as written, unsigned, and how many decimals it was written with."""
    digits = match.group("int").replace(",", "")
    decimals = match.groupdict().get("dec") or ""
    return Decimal(f"{digits}.{decimals}" if decimals else digits), len(decimals)


def _round(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _match(kind: str, match: re.Match[str], evidence: Evidence) -> Figure | bool:
    """The figure a typed number matches, True for a count, or False for nothing."""
    amount, decimals = _amount(match)
    figures = evidence.figures.values()
    if kind == "money":
        suffix = (match.group("suffix") or "").upper()
        for figure in (f for f in figures if f.unit == "cents"):
            dollars = Decimal(abs(figure.value)).scaleb(-2)
            if suffix == "" and decimals == 2 and dollars == amount:
                return figure
            if suffix == "" and decimals == 0 and _round(dollars, 0) == amount:
                return figure
            scale = {"K": 3, "M": 6}.get(suffix)
            if scale and decimals == 1 and _round(dollars.scaleb(-scale), 1) == amount:
                return figure
        return False
    if kind == "percent":
        for figure in (f for f in figures if f.unit == "bps"):
            pct = Decimal(abs(figure.value)).scaleb(-2)
            if decimals <= 2 and _round(pct, decimals) == amount:
                return figure
        return False
    if kind == "months":
        for figure in (f for f in figures if f.unit == "months_tenths"):
            months = Decimal(abs(figure.value)).scaleb(-1)
            if decimals <= 1 and _round(months, decimals) == amount:
                return figure
        return decimals == 0 and int(amount) in evidence.counts
    return int(amount) in evidence.counts
