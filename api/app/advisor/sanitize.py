"""Untrusted text, made safe to show a model.

Merchants and memos arrive from bank exports today and from SimpleFIN after ticket 075;
names, notes and rule patterns are typed into forms. Any of them can carry instructions
aimed at a model. This runs at the tool-result boundary **only**: stored data and screens
are untouched, because React already escapes what it renders and rewriting a merchant
name in the database would be a write the advisor is not allowed to make.

**Heuristics are not the boundary.** The boundary is that the advisor has nowhere to send
data (docs/ADVISOR.md#prompt-injection). This reduces how often a model reads an injection
at all, and makes the ones it does read harder to act on.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

WITHHELD = "[text withheld: resembled instructions]"
LINK_REMOVED = "[link removed]"

#: Characters kept per field, by what the field holds. Anything longer is cut with "…".
LIMITS = {"name": 60, "merchant": 60, "description": 80}
DEFAULT_LIMIT = 120

#: Phrases addressed to an assistant rather than describing a purchase. A bank memo has
#: no business saying any of these. Matched case-insensitively on the normalised text.
INSTRUCTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instructions?|prompts?|rules|above|previous|prior|earlier)\b",
    r"\bdisregard\b.{0,40}\b(instructions?|prompts?|rules|above|previous|prior)\b",
    r"\bforget\b.{0,30}\b(instructions?|everything|rules)\b",
    r"\bsystem\s*prompt\b",
    r"\b(new|updated|additional)\s+instructions?\b",
    r"\byou\s+(are|must|should|will)\s+(now\s+)?(an?\s+)?(ai|assistant|model|chatbot|claude|gpt)\b",
    r"\b(assistant|system|user|developer)\s*:",
    r"<\|[^|]{0,40}\|>",
    r"\[/?(inst|system|sys)\]",
    r"<\s*/?\s*(system|instructions?|assistant)\s*>",
    r"#{2,}\s*(instruction|system)",
    r"\b(call|use|invoke|run|execute)\s+(the\s+)?(\w+\s+)?(tool|function)s?\b",
    r"\b(reveal|print|show|repeat|output)\s+(your|the)\s+(system\s+)?(prompt|instructions?)\b",
    r"\b(tell|inform)\s+the\s+user\b",
    r"\bdo\s+not\s+(tell|mention|reveal)\b",
    r"\brespond\s+(only\s+)?with\b",
    r"\bprompt\s+injection\b",
]
_INSTRUCTION = re.compile("|".join(f"(?:{p})" for p in INSTRUCTION_PATTERNS), re.IGNORECASE)

#: Anything that could make a renderer or a person follow a link.
_URL = re.compile(
    r"(?:\b[a-z][a-z0-9+.\-]{1,20}://\S+)"  # scheme://…
    r"|(?:\b(?:data|javascript|mailto|file):\S+)"  # scheme-only URIs
    r"|(?:\bwww\.\S+)"  # www.…
    r"|(?:\b[\w\-]+(?:\.[\w\-]+)*\.[a-z]{2,24}/\S*)",  # bare domain with a path
    re.IGNORECASE,
)
_MD_IMAGE = re.compile(r"!\[([^\]]{0,200})\]\([^)]{0,500}\)")
_MD_LINK = re.compile(r"\[([^\]]{0,200})\]\([^)]{0,500}\)")
_MD_REF_USE = re.compile(r"!?\[([^\]]{0,200})\]\[[^\]]{0,100}\]")
_MD_REF_DEF = re.compile(r"\[[^\]]{1,100}\]:\s*\S+")
_HTML = re.compile(r"<[^<>]{0,300}>")
_WHITESPACE = re.compile(r"\s+")

#: Variation selectors and the Unicode tag block: invisible, and the usual tools of
#: "ASCII smuggling". Other invisible characters are caught by category below.
_SMUGGLING = re.compile("[︀-️\U000e0000-\U000e007f\U000e0100-\U000e01ef]")


@dataclass(frozen=True)
class Sanitized:
    text: str
    withheld: bool


def limit_for(field: str) -> int:
    """How many characters a `*_text` field keeps, from what it names."""
    stem = field.removesuffix("_text")
    for key, limit in LIMITS.items():
        if stem.endswith(key):
            return limit
    return DEFAULT_LIMIT


def _visible(text: str) -> str:
    """NFKC-normalised, with control, format, private-use and smuggling characters removed.

    Format characters (category Cf) are zero-width spaces and joiners, bidirectional
    overrides, and the tag block — all invisible on screen and all readable by a model.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _SMUGGLING.sub("", text)
    kept = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in "\t\n\r":
            kept.append(" ")
        elif category in {"Cc", "Cf", "Co", "Cs"}:
            continue
        else:
            kept.append(ch)
    return "".join(kept)


def looks_like_instructions(text: str, tool_names: Iterable[str] = ()) -> bool:
    """Whether text reads as addressed to a model, or names one of its tools."""
    if _INSTRUCTION.search(text):
        return True
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(name.lower())}\b", lowered) for name in tool_names)


def sanitize(value: str, *, field: str, tool_names: Iterable[str] = ()) -> Sanitized:
    """Make one untrusted string safe to put in front of a model.

    In order: normalise and strip invisible characters; withhold the whole value if it
    reads as instructions (checked on the full text, so a payload cannot hide past the
    truncation point); remove links, markdown link and image syntax — inline and
    reference-style — and HTML; collapse whitespace; truncate.
    """
    text = _visible(value)

    if looks_like_instructions(text, tool_names):
        return Sanitized(WITHHELD, withheld=True)

    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_REF_DEF.sub("", text)
    text = _MD_REF_USE.sub(r"\1", text)
    text = _URL.sub(LINK_REMOVED, text)
    text = _HTML.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()

    limit = limit_for(field)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return Sanitized(text, withheld=False)
