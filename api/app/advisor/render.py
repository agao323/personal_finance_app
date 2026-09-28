"""What a model sees of a tool result: formatted figures, each with its reference.

A tool returns a typed result — money in integer cents, percentages in basis points —
and **the model never sees it**. It sees this rendering, from one formatter:

    {"tool": "networth_get", "call": "c2", "as_of": "2026-09-27", "view": "household",
     "data": {"net_worth": "$412,388.14 [c2.net_worth]", ...}}

- **Figures arrive formatted.** The model copies `$412,388.14`; converting cents to dollars
  would be arithmetic, and it does none.
- **Every figure carries its reference** in square brackets. The model writes
  `{{c2.net_worth}}` in its answer and the server writes the value in — the
  Proof-Carrying Numbers shape in docs/ADVISOR.md#grounding. The rendering is lossless
  (cents to the cent, basis points to 0.01%), so the references can be rebuilt from a
  stored transcript with `figures_in`.
- **Untrusted text is marked by name.** Fields ending `_text` keep the suffix and pass
  through `sanitize.py`; the system prompt says what the suffix means.
- **No float, no Decimal.** A result carrying either is a bug in the tool — money is cents
  and ratios are fixed-point — and rendering refuses it rather than guessing.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app.advisor.sanitize import sanitize

#: The most a single tool result may occupy, rendered. Rows past it are dropped.
MAX_BYTES = 8_000

Unit = Literal["cents", "bps", "months_tenths"]

#: Field suffix → (unit, what the rendered key drops).
_SUFFIXES: dict[str, Unit] = {"_cents": "cents", "_bps": "bps", "_months_tenths": "months_tenths"}


@dataclass(frozen=True)
class Figure:
    """One figure a model can reference, and the only forms it may take in an answer."""

    ref: str
    unit: Unit
    value: int
    display: str


@dataclass
class Rendered:
    text: str
    figures: dict[str, Figure] = field(default_factory=dict)
    withheld: int = 0
    truncated: bool = False


def money(cents: int) -> str:
    """`123456` → `$1,234.56`; `-1234` → `-$12.34`. Exact: no rounding happens here."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def percent(bps: int) -> str:
    """`1234` → `12.34%`. Basis points are hundredths of a percent, shown in full."""
    return f"{Decimal(bps).scaleb(-2):.2f}%"


def months(tenths: int) -> str:
    """`234` → `23.4 months`."""
    return f"{Decimal(tenths).scaleb(-1):.1f} months"


def display(unit: Unit, value: int) -> str:
    if unit == "cents":
        return money(value)
    if unit == "bps":
        return percent(value)
    return months(value)


def _shown_key(key: str, suffix: str, unit: Unit) -> str:
    """The key a model sees for a figure.

    Money drops `_cents` — the value says `$`. Months keep `_months`: `runway_months`.
    Percentages become `_pct`, so a change in dollars and the same change in percent —
    `total_change_cents` and `total_change_bps` — cannot both render as `total_change`,
    which they did until a test caught one overwriting the other.
    """
    if unit == "months_tenths":
        return key.removesuffix("_tenths")
    if unit == "bps":
        return key.removesuffix(suffix) + "_pct"
    return key.removesuffix(suffix)


class _Walker:
    def __init__(self, call_id: str, tool_names: Iterable[str]) -> None:
        self.call_id = call_id
        self.tool_names = tuple(tool_names)
        self.figures: dict[str, Figure] = {}
        self.withheld = 0

    def value(self, key: str, value: Any, path: str) -> tuple[str, Any] | None:
        if value is None:
            return None
        for suffix, unit in _SUFFIXES.items():
            if key.endswith(suffix) and isinstance(value, int) and not isinstance(value, bool):
                shown = _shown_key(key, suffix, unit)
                ref = f"{self.call_id}.{path}{shown}"
                text = display(unit, value)
                self.figures[ref] = Figure(ref=ref, unit=unit, value=value, display=text)
                return shown, f"{text} [{ref}]"
        if key.endswith("_text") and isinstance(value, str):
            result = sanitize(value, field=key, tool_names=self.tool_names)
            self.withheld += result.withheld
            return key, result.text
        return key, self.plain(value, f"{path}{key}.")

    def plain(self, value: Any, path: str) -> Any:
        if isinstance(value, bool | int | str):
            return value
        if isinstance(value, dt.date):
            return value.isoformat()
        if isinstance(value, float | Decimal):
            raise TypeError(
                f"{self.call_id}: {path.rstrip('.')} is a {type(value).__name__}. Money is "
                "integer cents and ratios are fixed-point integers; never float or Decimal."
            )
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                pair = self.value(key, item, path)
                if pair is not None:
                    if pair[0] in out:
                        raise ValueError(f"{self.call_id}: two fields render as {pair[0]!r}")
                    out[pair[0]] = pair[1]
            return out
        if isinstance(value, list | tuple):
            return [self.plain(item, f"{path}{index}.") for index, item in enumerate(value)]
        return str(value)


def _dump(result: BaseModel) -> dict[str, Any]:
    dumped: dict[str, Any] = result.model_dump(mode="python")
    return dumped


def render(
    tool: str,
    call_id: str,
    result: BaseModel,
    *,
    tool_names: Iterable[str] = (),
    max_bytes: int = MAX_BYTES,
) -> Rendered:
    """The envelope a model sees, capped at `max_bytes` by dropping trailing rows."""
    data = _dump(result)
    envelope_fields = {key: data.pop(key) for key in ("as_of", "view", "stale") if key in data}
    truncated = False

    while True:
        walker = _Walker(call_id, tool_names)
        envelope: dict[str, Any] = {"tool": tool, "call": call_id}
        for key, value in envelope_fields.items():
            if value is not None:
                envelope[key] = walker.plain(value, "")
        if truncated:
            envelope["truncated"] = True
        envelope["data"] = walker.plain(data, "")
        text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode()) <= max_bytes:
            return Rendered(text, walker.figures, walker.withheld, truncated)
        lists = [(key, value) for key, value in data.items() if isinstance(value, list) and value]
        if not lists:
            note = {"tool": tool, "call": call_id, "truncated": True, "data": {}}
            return Rendered(json.dumps(note), {}, 0, True)
        longest = max(lists, key=lambda pair: len(pair[1]))[0]
        data[longest] = data[longest][:-1]
        truncated = True


#: A rendered figure and its reference, as `render` writes them.
_FIGURE = re.compile(
    r"(?P<display>-?\$[\d,]+\.\d{2}|-?\d+\.\d{2}%|-?\d+\.\d months) \[(?P<ref>c\d+(?:\.[\w]+)+)\]"
)


def figures_in(text: str) -> dict[str, Figure]:
    """Every figure in a stored rendering, keyed by reference.

    Lets the grounding check rebuild what earlier turns proved from the transcript alone,
    without a second store that could disagree with it.
    """
    found: dict[str, Figure] = {}
    for match in _FIGURE.finditer(text):
        shown = match["display"]
        if shown.endswith("%"):
            unit: Unit = "bps"
            value = int(Decimal(shown[:-1]).scaleb(2))
        elif shown.endswith("months"):
            unit = "months_tenths"
            value = int(Decimal(shown.split()[0]).scaleb(1))
        else:
            unit = "cents"
            value = int(Decimal(shown.replace("$", "").replace(",", "")).scaleb(2))
        found[match["ref"]] = Figure(ref=match["ref"], unit=unit, value=value, display=shown)
    return found
