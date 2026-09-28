"""Cheap, deterministic checks on every answer — shared with the evals' graders (ticket 102).

docs/ADVISOR.md#policy-checks-on-every-answer: a scaled-down version of the compliance gateway
a regulated adviser runs before a response is shown.

- **No products.** No tickers, fund names or fund issuers. The household's own institution
  and account names are exempt: "your Fidelity brokerage" names an account, not a product.
- **No claimed actions.** The advisor has no write tools, so "I've marked it used" is false.
- **No tax figures.** A tax limit, bracket or rate stated as a number may be a year stale.
- **Scope.** A scoped figure — net worth, a balance, runway's liquid assets — is labelled Mine
  or Household; spending is never called anyone's share.

These are heuristics, not a boundary. They catch the common failures cheaply, and a failure
earns one regeneration; the evals measure what they miss.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advisor.grounding import Evidence
from app.models import Account, Institution
from app.schemas.advisor import FigureCheck, FigureStatus, PolicyCheck, PolicyNote

#: Fund issuers and fund families. Maintained by hand; add to it when an eval finds a gap.
ISSUERS: tuple[str, ...] = (
    "Vanguard",
    "Fidelity",
    "Schwab",
    "Charles Schwab",
    "BlackRock",
    "iShares",
    "SPDR",
    "State Street",
    "Invesco",
    "T. Rowe Price",
    "T Rowe Price",
    "JPMorgan",
    "J.P. Morgan",
    "Franklin Templeton",
    "PIMCO",
    "American Funds",
    "Capital Group",
    "Dimensional",
    "WisdomTree",
    "ProShares",
    "Direxion",
    "ARK Invest",
    "Avantis",
    "Nuveen",
    "TIAA",
    "Janus Henderson",
    "Dodge & Cox",
    "Wealthfront",
    "Betterment",
)

#: Common tickers. Mutual-fund tickers (five letters ending in X) are caught by pattern.
TICKERS: frozenset[str] = frozenset(
    {
        "VTI",
        "VOO",
        "VT",
        "VXUS",
        "VEA",
        "VWO",
        "BND",
        "BNDX",
        "VIG",
        "VYM",
        "VNQ",
        "VGT",
        "SPY",
        "IVV",
        "QQQ",
        "QQQM",
        "DIA",
        "IWM",
        "ITOT",
        "IXUS",
        "IEFA",
        "IEMG",
        "AGG",
        "SCHB",
        "SCHD",
        "SCHX",
        "SCHF",
        "SCHZ",
        "SPLG",
        "SPTM",
        "RSP",
        "TLT",
        "SHY",
        "GLD",
        "ARKK",
        "SGOV",
        "BIL",
        "JEPI",
        "VUG",
        "VTV",
        "MUB",
        "TIP",
        "VTIP",
        "BRK.B",
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "GOOG",
        "META",
        "TSLA",
    }
)
_MUTUAL_FUND = re.compile(r"\b[A-Z]{4}X\b")
_TICKER = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b")

_CLAIMED = re.compile(
    r"(?i)\b(?:I've|I have|I)\s+(?:just\s+|now\s+|already\s+|gone ahead and\s+|went ahead and\s+)?"
    r"(?:marked|moved|transferred|updated|changed|recategori[sz]ed|categori[sz]ed|set up|"
    r"created|deleted|removed|added|saved|paid|scheduled|cancel(?:l)?ed|renamed|edited|applied|"
    r"logged|recorded|fixed)\b"
)
_DONE = re.compile(r"(?im)^\s*(?:done|all set)[.!]")

_TAX_TERMS = re.compile(
    r"(?i)(?:\b(?:tax(?:es|ed)?|IRS|IRA|HSA|FSA|Roth|capital gains|FICA|estate|gift|deduction|"
    r"deductible|RMD|457)\b|\b40[13]\s?\([kb]\))"
)
_LIMIT_TERMS = re.compile(
    r"(?i)\b(?:limit|limits|bracket|brackets|rate|rates|threshold|phase-?out|exemption|"
    r"standard deduction|cap|maximum|max|allowance|contribute up to|up to)\b"
)
_NUMBER = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kKM]?|\d+(?:\.\d+)?\s?%")
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")

_SCOPE_LABEL = re.compile(r"(?i)\b(?:mine|household|your (?:share|ownership|stake))\b")
_SPEND_SHARE = re.compile(
    r"(?i)\b(?:your|my|his|her|their|[A-Z][a-z]+'s|partner's)\s+(?:share|portion|part)\s+of\s+"
    r"(?:the\s+|your\s+|our\s+)?(?:household\s+)?"
    r"(?:spend(?:ing)?|expenses?|groceries|dining|bills|burn|costs?|outflows?|cash\s?flow|income)"
)


def household_names(session: Session) -> set[str]:
    """Institution and account names: a product name inside one of these names an account."""
    names = set(session.execute(select(Institution.name)).scalars())
    names |= set(session.execute(select(Account.name)).scalars())
    return {n for n in names if n}


def _exempt(term: str, names: Iterable[str]) -> bool:
    folded = term.casefold()
    return any(folded in name.casefold() for name in names)


def check(
    text: str,
    *,
    figures: Sequence[FigureCheck],
    evidence: Evidence,
    exempt_names: Iterable[str] = (),
) -> list[PolicyNote]:
    """Every rule the answer breaks, each once, in a fixed order."""
    names = list(exempt_names)
    notes: list[PolicyNote] = []

    products = [
        issuer
        for issuer in ISSUERS
        if re.search(rf"(?i)\b{re.escape(issuer)}\b", text) and not _exempt(issuer, names)
    ]
    products += [
        token
        for token in dict.fromkeys(_TICKER.findall(text))
        if (token in TICKERS or _MUTUAL_FUND.fullmatch(token)) and not _exempt(token, names)
    ]
    if products:
        notes.append(
            PolicyNote(
                check=PolicyCheck.TICKER_OR_ISSUER,
                message="Names a specific fund, ticker or fund company. Recommendations should "
                "be about fund types, not products.",
            )
        )

    if _CLAIMED.search(text) or _DONE.search(text):
        notes.append(
            PolicyNote(
                check=PolicyCheck.CLAIMED_ACTION,
                message="Says something was changed. The advisor cannot change anything; "
                "changes are made on the app's screens.",
            )
        )

    grounded = [(f.start, f.end) for f in figures if f.status is not FigureStatus.UNVERIFIED]
    for sentence in _SENTENCE.finditer(text):
        body = sentence[0]
        if not (_TAX_TERMS.search(body) and _LIMIT_TERMS.search(body)):
            continue
        for number in _NUMBER.finditer(body):
            start, end = sentence.start() + number.start(), sentence.start() + number.end()
            if not any(a <= start and end <= b for a, b in grounded):
                notes.append(
                    PolicyNote(
                        check=PolicyCheck.TAX_FIGURE,
                        message="States a tax limit, bracket or rate as a number. These change "
                        "every year; check the current figure with the IRS or a tax professional.",
                    )
                )
                break
        if notes and notes[-1].check is PolicyCheck.TAX_FIGURE:
            break

    scoped = any(
        f.source is not None and evidence.views.get(f.source.call_id) is not None
        for f in figures
        if f.status is not FigureStatus.UNVERIFIED
    )
    if (scoped and not _SCOPE_LABEL.search(text)) or _SPEND_SHARE.search(text):
        notes.append(
            PolicyNote(
                check=PolicyCheck.SCOPE_LABEL,
                message="A figure that depends on ownership should say Mine or Household, and "
                "spending is never anyone's share.",
            )
        )
    return notes
