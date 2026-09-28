"""An answer made safe to show, and the sources under it.

**Post-processing** is the first of three independent layers against exfiltration through the
browser (docs/ADVISOR.md#prompt-injection): this strips every way markdown can make a browser
fetch or a person click — images and links, **inline and reference-style, including the
`[1]: https://…` definitions** that EchoLeak used — plus autolinks, bare URLs and raw HTML. The
renderer has no `a` or `img`, and the page's CSP allows only `'self'`; each layer holds without
the others.

**Screen tokens** are the one way an answer points somewhere: `[[screen:cards]]`, from the
`Screen` enum, which the web maps to its own routes. Any other token is removed.

**Sources are the system's**, assembled from the turn's tool calls. The model cannot leave one
out or make one up.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.advisor.tools import ToolOutcome
from app.schemas.advisor import Citation, LimitationKind, Lookup, LookupStatus, Screen

NOTE_LIMITATION = "note_limitation"

_SCREEN_TOKEN = re.compile(r"\[\[screen:([^\]\s]*)\]\]")
_KNOWN = frozenset(s.value for s in Screen)
#: Held aside while stripping, so link rules cannot touch a screen token.
_HOLD = "\x00{}\x00"

_STEPS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Reference definitions: `[1]: https://…` and `[id]: <…> "title"`, on their own line.
    (
        re.compile(
            r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*\S+"
            r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$\n?"
        ),
        "",
    ),
    # Images, inline and reference-style: gone, alt text and all.
    (re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)"), ""),
    (re.compile(r"!\[[^\]\n]*\]\[[^\]\n]*\]"), ""),
    # Links, inline and reference-style: the words stay, the destination goes.
    (re.compile(r"\[([^\]\n]+)\]\([^)\n]*\)"), r"\1"),
    (re.compile(r"\[([^\]\n]+)\]\[[^\]\n]*\]"), r"\1"),
    # Autolinks and raw HTML.
    (re.compile(r"<(?:[a-zA-Z][a-zA-Z0-9+.-]*:|www\.)[^>\s]*>"), ""),
    (re.compile(r"</?[a-zA-Z][^>\n]*>"), ""),
    (re.compile(r"<!--.*?-->", re.DOTALL), ""),
    # Anything else URL-shaped.
    (re.compile(r"(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+"), "[link removed]"),
    (
        re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|co|app|dev|xyz|info|ly|me)/\S*"),
        "[link removed]",
    ),
)


def clean(text: str) -> str:
    """The answer with every link, image and tag removed, and only known screen tokens kept."""
    kept: list[str] = []

    def hold(match: re.Match[str]) -> str:
        if match[1] not in _KNOWN:
            return ""
        kept.append(match[0])
        return _HOLD.format(len(kept) - 1)

    text = _SCREEN_TOKEN.sub(hold, text)
    for pattern, replacement in _STEPS:
        text = pattern.sub(replacement, text)
    for index, token in enumerate(kept):
        text = text.replace(_HOLD.format(index), token)
    return text.replace("\x00", "")


def lookup(outcome: ToolOutcome) -> Lookup:
    """One call for the "show lookups" control: what, with which arguments, how many rows."""
    return Lookup(
        call_id=outcome.call_id,
        tool=outcome.tool,
        label=outcome.label,
        arguments=outcome.arguments,
        status=outcome.status,
        row_count=outcome.row_count,
        latency_ms=outcome.latency_ms,
        as_of=outcome.as_of,
    )


def citations(outcomes: Iterable[ToolOutcome]) -> list[Citation]:
    """A source line for every successful lookup: as of when, in which view, and if stale."""
    return [
        Citation(
            call_id=o.call_id,
            tool=o.tool,
            label=o.label,
            as_of=o.as_of,
            view=o.view,
            stale=o.stale,
        )
        for o in outcomes
        if o.status is LookupStatus.OK and o.tool != NOTE_LIMITATION
    ]


def limitations(outcomes: Iterable[ToolOutcome]) -> list[LimitationKind]:
    """The data this turn's question needed and the app does not have, in the order noted."""
    seen: list[LimitationKind] = []
    for o in outcomes:
        if o.tool == NOTE_LIMITATION and o.status is LookupStatus.OK:
            kind = LimitationKind(o.args["capability"])
            if kind not in seen:
                seen.append(kind)
    return seen
