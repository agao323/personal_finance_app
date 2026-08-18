"""The categorisation rules engine: merchant pattern → category, ordered, first match wins.

Imported categories are mediocre, and a spending chart built on them is subtly wrong in
a way nobody can see. A user-editable rule set is what makes the breakdowns trustworthy
enough to act on — see docs/ARCHITECTURE.md#categories--categorization_rules.

Four properties hold, and each of them is load-bearing:

**A manual category is never overwritten.** This is the entire reason
``transactions.category_source`` exists. :func:`apply_rules` skips any transaction whose
source is ``manual``, unconditionally — not "unless the rule is newer", not "unless the
rule is more specific". A human looked at that row and decided; a pattern does not get
to argue. Ticket 023 is what writes ``manual``, so this protection and that write path
are only meaningful as a pair.

**Order is total and deterministic.** Rules run by ``priority`` ascending, ties broken by
``id`` — creation order. Without the tie-break, two rules at the default priority would
match in whatever order Postgres felt like returning them, and re-running the engine
could produce a different answer each time. First match wins; later rules never see the
transaction.

**Re-running over all history is idempotent.** A row is written only when the rule set
would actually change ``(category_id, category_source)``, so a second run reports zero
changes and touches no rows.

**Re-running is never destructive.** A rule matching nothing leaves the transaction
uncategorised — that is a real state the spend view surfaces as the prompt to write a
rule, not an error. And a row previously categorised by a rule keeps that category when
the rule is deleted, rather than being cleared. The alternative makes an accidental
apply against an empty rule set wipe the categorisation of every transaction in the
database, which is exactly the kind of surprise this app cannot afford. The cost is a
stale category that survives its rule until another rule claims the row; that is
recoverable, mass erasure is not.

## Untrusted patterns

A `regex` rule is user-supplied code running against every transaction in the database.
Two failure modes, handled separately:

- **Malformed.** ``re.compile`` raises; :func:`validate_pattern` turns that into
  :class:`InvalidPatternError`, which the router reports as a 422. A pattern is validated
  when it is *written*, so a broken one never reaches storage and cannot break a later
  apply that had nothing to do with it.
- **Catastrophically backtracking.** ``(a+)+$`` against thirty characters is 2^30 steps.
  Python's ``re`` has no timeout and cannot be interrupted mid-match, so there is no way
  to make a single match safe with the standard library. Three bounds instead:
  :func:`has_nested_quantifier` rejects the classic exponential shape at write time; the
  subject fed to a match is truncated to :data:`MAX_SUBJECT_CHARS`; and
  :func:`apply_rules` holds a wall-clock budget checked between transactions, so a run
  that has gone wrong stops rather than pinning a worker for ever.

None of that is a proof. A hard guarantee needs a different engine (RE2, or the
``regex`` module's ``timeout=``), which is a dependency this ticket does not add for one
household typing its own patterns. If patterns ever come from anywhere but the
household, revisit it.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CategorySource, MatchType
from app.models.transaction import CategorizationRule, Transaction

#: Applied when a rule is created without one. Ties break by id, so rules created at the
#: default priority run in creation order — the least surprising reading of "first match
#: wins" for someone who never touches priority at all.
DEFAULT_PRIORITY = 100

#: Applied when a rule is created without one. `contains` is what a person means by
#: "categorise anything from Whole Foods".
DEFAULT_MATCH_TYPE = MatchType.CONTAINS

#: The most text any pattern is matched against. `merchant` is capped at 255 by the
#: schema but `description` is unbounded TEXT, and match cost scales with subject length.
MAX_SUBJECT_CHARS = 512

#: Wall-clock ceiling on a whole :func:`apply_rules` run, in seconds. Generous for a
#: household ledger — tens of thousands of rows against a handful of rules is
#: milliseconds — and low enough that a pathological pattern fails fast.
APPLY_BUDGET_SECONDS = 10.0


class InvalidPatternError(ValueError):
    """A user-supplied pattern the engine refuses to store or run."""


class RuleBudgetError(RuntimeError):
    """An apply run outlived :data:`APPLY_BUDGET_SECONDS`.

    Raised rather than returning a partial result: the caller must not commit half a
    re-categorisation and report it as a success.
    """


# ── pattern safety ────────────────────────────────────────────────────────────

#: `{2,}` and `{,}` repeat without an upper bound. `{2,5}` is bounded work, so it is not
#: what makes a pattern explode and is deliberately not matched here.
_UNBOUNDED_BRACE = re.compile(r"\{\d*,\}")


def _structural(pattern: str) -> list[tuple[int, str]]:
    """The ``(index, char)`` pairs that carry regex structure.

    Escaped characters and the contents of a character class are dropped, so ``\\(`` is
    not read as a group and ``[+*]`` is not read as two quantifiers.
    """
    out: list[tuple[int, str]] = []
    index = 0
    in_class = False

    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if in_class:
            in_class = char != "]"
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            continue
        out.append((index, char))
        index += 1

    return out


def _repeats_unboundedly(pattern: str, index: int) -> bool:
    """True when an unbounded repetition starts at ``index``.

    ``?`` is excluded on purpose: ``(a+)?`` is linear, and rejecting it would refuse a
    perfectly ordinary pattern.
    """
    char = pattern[index]
    if char in "*+":
        return True
    return char == "{" and _UNBOUNDED_BRACE.match(pattern, index) is not None


def has_nested_quantifier(pattern: str) -> bool:
    """True when an unbounded repetition wraps a group that itself repeats unboundedly.

    ``(a+)+``, ``(a*)*`` and ``(\\d{2,})+`` are the shape behind almost every real
    catastrophic-backtracking report, and each of them is something a person writing a
    merchant pattern has no reason to type.

    A heuristic, not a decision procedure. ``(a|a)+`` is exponential too and is not
    caught here — detecting overlapping alternations properly means implementing the
    matcher. The wall-clock budget in :func:`apply_rules` is what covers the rest.
    """
    structural = _structural(pattern)
    open_groups: list[int] = []

    for index, char in structural:
        if char == "(":
            open_groups.append(index)
        elif char == ")" and open_groups:
            opened_at = open_groups.pop()
            after = index + 1
            if after >= len(pattern) or not _repeats_unboundedly(pattern, after):
                continue
            if any(
                _repeats_unboundedly(pattern, inner)
                for inner, _ in structural
                if opened_at < inner < index
            ):
                return True

    return False


def validate_pattern(pattern: str, match_type: MatchType) -> None:
    """Raise :class:`InvalidPatternError` if this pattern must not be stored.

    Only `regex` patterns can fail — a literal is always a valid literal.
    """
    if match_type is not MatchType.REGEX:
        return

    try:
        re.compile(pattern)
    except re.error as error:
        raise InvalidPatternError(f"Invalid regular expression: {error}") from error

    if has_nested_quantifier(pattern):
        raise InvalidPatternError(
            "Rejected: a repeated group that itself repeats (for example `(a+)+`) can "
            "take exponential time to match. Rewrite the pattern without the nesting."
        )


# ── matching ──────────────────────────────────────────────────────────────────

#: Literal matchers, keyed by match type. Both arguments arrive case-folded.
#:
#: Matching is case-insensitive throughout. Institutions are wildly inconsistent about
#: case — "WHOLE FOODS", "Whole Foods Mkt", "whole foods #123" are the same merchant —
#: and a rule that silently misses two of the three is worse than no rule, because the
#: chart still looks plausible.
_LITERAL_MATCHERS: dict[MatchType, Callable[[str, str], bool]] = {
    MatchType.CONTAINS: lambda subject, pattern: pattern in subject,
    MatchType.EQUALS: lambda subject, pattern: subject == pattern,
    MatchType.STARTS_WITH: lambda subject, pattern: subject.startswith(pattern),
}


@dataclass(frozen=True)
class CompiledRule:
    """One rule, ready to run. Build these with :func:`compile_rules`, never by hand —
    it is what guarantees ``regex`` is populated exactly when ``match_type`` is regex."""

    id: int
    pattern: str
    match_type: MatchType
    category_id: int
    priority: int
    regex: re.Pattern[str] | None = None

    def matches(self, subject: str) -> bool:
        if self.regex is not None:
            return self.regex.search(subject) is not None
        return _LITERAL_MATCHERS[self.match_type](subject.casefold(), self.pattern.casefold())


def subject_of(transaction: Transaction) -> str:
    """The text a rule is matched against.

    Merchant first, description as the fallback. Rules are described as merchant
    patterns, but plenty of CSV exports put the merchant *in* the description and leave
    the merchant column empty; ignoring it there would make rules silently useless for a
    whole institution. Concatenating both instead was rejected — ``equals`` and
    ``starts_with`` stop meaning anything against a concatenation.
    """
    raw = transaction.merchant or transaction.description or ""
    return raw.strip()[:MAX_SUBJECT_CHARS]


def compile_rules(rules: Iterable[CategorizationRule]) -> list[CompiledRule]:
    """Validate, compile, and order a rule set.

    The returned list is in run order: ``priority`` ascending, then ``id`` — total and
    deterministic, which is what makes re-running the engine reproducible.

    Raises :class:`InvalidPatternError` if any stored pattern no longer compiles. That
    should be unreachable, because patterns are validated on write; if it ever fires,
    something wrote to ``categorization_rules`` without going through the router.
    """
    compiled: list[CompiledRule] = []

    for rule in rules:
        regex: re.Pattern[str] | None = None
        if rule.match_type is MatchType.REGEX:
            validate_pattern(rule.pattern, rule.match_type)
            regex = re.compile(rule.pattern, re.IGNORECASE)
        compiled.append(
            CompiledRule(
                id=rule.id,
                pattern=rule.pattern,
                match_type=rule.match_type,
                category_id=rule.category_id,
                priority=rule.priority,
                regex=regex,
            )
        )

    return sorted(compiled, key=lambda rule: (rule.priority, rule.id))


def first_match(rules: Sequence[CompiledRule], subject: str) -> CompiledRule | None:
    """The first rule in run order that matches, or ``None``.

    ``None`` is an ordinary answer, not a failure: an unmatched transaction stays
    uncategorised and shows up in the spend view's uncategorised bucket, which is the
    prompt to write a rule. Guessing would be worse than leaving it blank.
    """
    if not subject:
        return None
    return next((rule for rule in rules if rule.matches(subject)), None)


# ── applying ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ApplyResult:
    """What a run did.

    ``examined`` is how many transactions were considered, ``categorised`` how many rows
    actually changed — not how many matched. A rule re-matching a row it already set
    changes nothing and is not counted, which is what makes a second run report zero and
    proves idempotency to the caller rather than just to a test.

    ``manual_preserved`` counts examined transactions skipped because a human had already
    decided. It is the number that makes the guarantee visible in the response.
    """

    examined: int
    categorised: int
    manual_preserved: int


def load_rules(session: Session) -> list[CategorizationRule]:
    """Every rule, in run order."""
    return list(
        session.execute(
            select(CategorizationRule).order_by(CategorizationRule.priority, CategorizationRule.id)
        )
        .scalars()
        .all()
    )


def apply_rules(
    session: Session,
    *,
    only_uncategorised: bool = False,
    budget_seconds: float = APPLY_BUDGET_SECONDS,
) -> ApplyResult:
    """Run the rule set over stored transactions.

    Safe to run over all history, as often as you like. Flushes but does not commit —
    the caller owns the transaction, so a failure part-way leaves nothing behind.

    ``only_uncategorised`` narrows the examined set to rows with no category. It is an
    optimisation, not a safety mechanism: the full run is equally safe, because manual
    rows are skipped either way. Note that a transaction a human explicitly *cleared*
    has ``category_id IS NULL`` with source ``manual`` — it is in the narrowed set and
    is still skipped, so "no category" stays a decision the engine respects.
    """
    rules = compile_rules(load_rules(session))

    query = select(Transaction).order_by(Transaction.id)
    if only_uncategorised:
        query = query.where(Transaction.category_id.is_(None))

    deadline = time.monotonic() + budget_seconds
    examined = 0
    categorised = 0
    manual_preserved = 0

    for transaction in session.execute(query).scalars():
        examined += 1

        # The whole point of `category_source`. No exceptions, no tie-breaks, no
        # "unless the rule is newer" — a human decision outranks a pattern.
        if transaction.category_source == CategorySource.MANUAL:
            manual_preserved += 1
            continue

        # Checked between transactions rather than inside a match, because `re` cannot
        # be interrupted mid-match. Bounds a run that has gone wrong; does not bound a
        # single pathological match. See the module docstring.
        if time.monotonic() > deadline:
            raise RuleBudgetError(
                f"Rule application exceeded {budget_seconds:g}s after {examined} "
                "transactions. A pattern is likely backtracking catastrophically."
            )

        match = first_match(rules, subject_of(transaction))
        if match is None:
            continue

        # Idempotency lives here: only count and write a real change.
        if (transaction.category_id, transaction.category_source) == (
            match.category_id,
            CategorySource.RULE,
        ):
            continue

        transaction.category_id = match.category_id
        transaction.category_source = CategorySource.RULE
        categorised += 1

    session.flush()

    return ApplyResult(
        examined=examined, categorised=categorised, manual_preserved=manual_preserved
    )
