"""CSV import: parse a file, work out what it would change, and say so.

Ticket 020 is everything up to and including the plan. Nothing here writes.

Three things make a CSV importer either trustworthy or quietly wrong, and all three
are decided in this module.

**The preview is the product.** Importing a real bank export is the one moment this
app touches data it cannot regenerate. So the parse produces a *plan* — a per-row
create/update/skip with the errors attached to the row that caused them — and the
route that writes takes the same plan and executes it. A count of "37 rows imported"
is not a safety net; a row that says "row 14: amount '12.345' has more than two
decimal places" is.

**Institutions disagree about signs.** Some export a $12 coffee as `-12.00`, some as
`12.00`. There is no way to detect which from the file alone — a credit card export
of a month with no refunds is all one sign either way — so it is configuration, not
inference: :attr:`ColumnMapping.invert_amount`, persisted per account in
``import_mappings`` so the second import of the same export needs no thought.
Storage is always outflow-negative.

**Two coffees are two coffees.** See :func:`derive_external_id`.

Amounts are parsed from the string with :class:`~decimal.Decimal` and never through
``float``. A row whose amount does not round-trip at 2dp is rejected rather than
rounded, because silently turning ``12.345`` into ``12.35`` is a cent that nobody
will ever find again.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.system import ImportMapping
from app.models.transaction import Transaction
from app.schemas.import_csv import ColumnMapping

#: Row verdicts. Plain strings because `PreviewRow.action` is a plain string in the
#: frozen contract, and an enum here would only have to be flattened again.
CREATE = "create"
UPDATE = "update"
SKIP = "skip"

TWO_PLACES = Decimal("0.01")

#: Date formats tried against the file, most specific first.
#:
#: Deliberately no day-first slash format. `05/06/2026` is the 5th of June in half the
#: world and the 6th of May in the other half, and there is nothing in a CSV that
#: says which — accepting both would make the choice a coin flip on a file where every
#: day happens to be ≤ 12. A day-first export is re-exported as ISO instead. The
#: ticket asks this code to reject rather than guess, and this is the guess it would
#: otherwise make.
#:
#: `%y` is tried before `%Y` because `strptime` happily reads "26" as the year 26 AD
#: under `%Y`, so the four-digit pattern would otherwise swallow two-digit years.
DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
)

#: Header names, normalised, that map onto each transaction field. First match wins,
#: and a header is only claimed once — which is what makes a file whose only text
#: column is "Description" put that text in `merchant`, where the categorisation
#: rules in ticket 022 will look for it, rather than leaving merchant empty.
HEADER_CANDIDATES: dict[str, tuple[str, ...]] = {
    "posted_at": (
        "posteddate",
        "postingdate",
        "postdate",
        "posted",
        "transactiondate",
        "date",
        "datetime",
    ),
    "amount": ("amount", "transactionamount", "amountusd", "value"),
    "external_id": (
        "transactionid",
        "externalid",
        "referenceid",
        "referencenumber",
        "reference",
        "id",
    ),
    "merchant": ("merchant", "payee", "name", "description", "originaldescription", "details"),
    "description": ("description", "memo", "notes", "details", "originaldescription"),
}

#: Fields the upsert owns. `category_id`, `category_source` and `transfer_group_id`
#: are deliberately absent — see :func:`plan_import`.
CONTENT_FIELDS = ("posted_at", "amount", "merchant", "description")

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]")
# The \u00a0 is spelled out rather than typed: some exports use a non-breaking
# space as a thousands separator, and an invisible literal inside a character
# class is unreadable and easy to delete by accident.
_CURRENCY_NOISE = re.compile("[,$\\s\u00a0]")
_WHITESPACE_RUN = re.compile(r"\s+")


class CsvFormatError(Exception):
    """The file cannot be interpreted at all.

    Distinct from a row-level problem on purpose. A bad row is data to show the user;
    a file with no header, or no column that could be a date, has nothing to preview
    and no mapping to display, so there is no useful dry run to return.
    """


# ── parsed shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedRow:
    """One CSV row, resolved as far as it could be.

    ``errors`` is per-row rather than accumulated at the file level because that is
    the difference between "3 rows were skipped" and "row 14's date '31/02/2026'
    isn't a date". Only the second one can be acted on.
    """

    row_number: int
    posted_at: dt.date | None = None
    amount: Decimal | None = None
    merchant: str | None = None
    description: str | None = None
    external_id: str | None = None
    action: str = SKIP
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.posted_at is not None and self.amount is not None


@dataclass(frozen=True)
class ImportPlan:
    """What a commit of this file would do. Produced without writing anything."""

    account_id: int
    mapping: ColumnMapping
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for row in self.rows if row.action == action)

    @property
    def writable(self) -> list[ParsedRow]:
        """Rows the commit will actually send to the database.

        Unchanged rows are included. They are *reported* as skipped, because nothing
        about the data moves, but they are still upserted: branching the write on what
        an earlier read saw is exactly the read-then-write race the unique index
        exists to remove.
        """
        return [row for row in self.rows if row.is_valid and row.external_id is not None]


@dataclass(frozen=True)
class ImportOutcome:
    """The result of a commit."""

    created: int
    updated: int
    skipped: int
    errors: list[str] = field(default_factory=list)


# ── field parsing ─────────────────────────────────────────────────────────────


def normalise_header(header: str) -> str:
    """`" Posted Date "` and `"posted_date"` are the same column."""
    return _NON_ALPHANUMERIC.sub("", header.lower())


def normalise_text(value: str) -> str | None:
    """Collapse whitespace; empty becomes ``None``.

    ``None`` rather than ``""`` so that a blank memo and a missing memo compare equal
    when deciding whether a re-import actually changed anything.
    """
    collapsed = _WHITESPACE_RUN.sub(" ", value).strip()
    return collapsed or None


def parse_amount(raw: str, invert: bool = False) -> Decimal:
    """Parse a money cell into an exact 2dp :class:`~decimal.Decimal`.

    Raises :class:`ValueError` rather than guessing. The 2dp check is the important
    one: storage is ``NUMERIC(19,2)`` and the wire format is integer cents, so a value
    with more precision than that cannot survive a round trip. Rounding it here would
    hide a real disagreement with the institution's own figures.

    ``invert`` flips the sign for institutions that export debits as positive.
    Applied after parsing so the sign convention is one decision in one place.
    """
    text = raw.strip()
    if not text:
        raise ValueError("amount is empty")

    negative = False
    # Accounting notation: (12.34) is -12.34.
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    text = _CURRENCY_NOISE.sub("", text).lstrip("+")

    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"amount {raw.strip()!r} is not a number") from None

    if not value.is_finite():
        raise ValueError(f"amount {raw.strip()!r} is not a finite number")

    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError(f"amount {raw.strip()!r} has more than two decimal places")

    if negative:
        value = -value
    if invert:
        value = -value

    try:
        # Adding zero normalises -0.00 to 0.00, so a zero-amount row hashes the same
        # way whichever sign convention produced it.
        return value.quantize(TWO_PLACES) + Decimal(0)
    except InvalidOperation:
        raise ValueError(f"amount {raw.strip()!r} is out of range") from None


def detect_date_format(values: Sequence[str]) -> str | None:
    """Pick one format for the whole column, or ``None`` if nothing fits.

    Once per file, not once per row. Deciding per row is how a file ends up with
    January the 2nd and February the 1st both read from `01/02`, and the result looks
    entirely plausible. The format that parses the most cells wins, so a single typo
    does not disqualify the format the rest of the file is in — that row gets its own
    error instead.
    """
    best: str | None = None
    best_score = 0

    for candidate in DATE_FORMATS:
        score = 0
        for value in values:
            try:
                dt.datetime.strptime(value, candidate)
            except ValueError:
                continue
            score += 1
        if score > best_score:
            best, best_score = candidate, score

    return best


def parse_date(value: str, date_format: str) -> dt.date:
    """Parse one cell under the format chosen for the file."""
    try:
        return dt.datetime.strptime(value.strip(), date_format).date()
    except ValueError:
        raise ValueError(f"date {value.strip()!r} does not match {date_format}") from None


# ── identity ──────────────────────────────────────────────────────────────────


def derive_external_id(
    account_id: int,
    posted_at: dt.date,
    amount: Decimal,
    merchant: str | None,
    description: str | None,
    occurrence: int,
) -> str:
    """A stable id for a row the institution did not identify.

    A content hash on its own is wrong, and wrong in the worst way: two coffees at the
    same shop on the same day for the same amount hash identically, the second upserts
    over the first, and one of them disappears. Nothing fails; a category total is
    just quietly low, and you find out months later, if ever.

    So the hash covers the row's content **plus its occurrence index within
    (account_id, posted_at, amount, merchant)** — the second identical coffee is
    occurrence 1 and survives. See docs/ARCHITECTURE.md#transactions.

    The index is counted in file order, which for any export sorted by date means a
    genuinely new transaction on an already-imported day lands at the end of its group
    and leaves the existing ids alone. Reordering the rows *within* one such group
    would shuffle the ids; no content-derived identity can avoid that, and the fix
    when it matters is an export that carries a real transaction id.

    Prefixed `csv:` so a derived id is never mistaken for one the bank issued.
    """
    payload = "\x1f".join(
        (
            str(account_id),
            posted_at.isoformat(),
            f"{amount:.2f}",
            (merchant or "").casefold(),
            (description or "").casefold(),
            str(occurrence),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"csv:{digest[:32]}"


def group_key(
    posted_at: dt.date, amount: Decimal, merchant: str | None
) -> tuple[dt.date, Decimal, str]:
    """The bucket an occurrence index counts within."""
    return posted_at, amount, (merchant or "").casefold()


# ── mappings ──────────────────────────────────────────────────────────────────


def detect_mapping(headers: Sequence[str]) -> ColumnMapping:
    """Guess which column is which from the header row.

    Raises :class:`CsvFormatError` when there is no plausible date or amount column —
    without both there is nothing to preview and no mapping worth showing.
    """
    normalised = {normalise_header(h): h for h in headers if h}
    claimed: set[str] = set()
    resolved: dict[str, str] = {}

    for field_name, candidates in HEADER_CANDIDATES.items():
        for candidate in candidates:
            header = normalised.get(candidate)
            if header is not None and header not in claimed:
                claimed.add(header)
                resolved[field_name] = header
                break

    missing = [name for name in ("posted_at", "amount") if name not in resolved]
    if missing:
        if "amount" in missing and {"debit", "credit"} <= set(normalised):
            raise CsvFormatError(
                "this file splits debits and credits into two columns, which the "
                "import mapping cannot express — re-export with a single signed "
                "amount column"
            )
        raise CsvFormatError(
            f"could not find a column for: {', '.join(missing)} "
            f"(headers seen: {', '.join(h for h in headers if h)})"
        )

    return ColumnMapping(**resolved)


def load_saved_mapping(session: Session, account_id: int) -> ColumnMapping | None:
    """The mapping remembered for this account, if any.

    Preview has no way to be handed a mapping — its route takes a file and an account
    id and nothing else — so this is how the second import of the same export gets the
    sign convention right without the user restating it.

    A row that no longer validates against the contract is ignored rather than raised:
    a stale saved mapping should degrade to detection, not break the import.
    """
    saved = session.execute(
        select(ImportMapping)
        .where(ImportMapping.account_id == account_id)
        .order_by(ImportMapping.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if saved is None:
        return None
    try:
        return ColumnMapping.model_validate(saved.column_map)
    except ValidationError:
        return None


def save_mapping(
    session: Session, account_id: int, name: str, mapping: ColumnMapping
) -> ImportMapping:
    """Persist a mapping for reuse, replacing one of the same name.

    Upsert rather than insert for the same reason every other write here is: saving
    twice under one name is a correction, not an error.
    """
    column_map = mapping.model_dump(exclude_none=True)
    statement = (
        insert(ImportMapping)
        .values(account_id=account_id, name=name, column_map=column_map)
        .on_conflict_do_update(
            constraint="uq_mapping_account_name", set_={"column_map": column_map}
        )
        .returning(ImportMapping)
    )
    saved = session.execute(statement).scalar_one()
    session.flush()
    return saved


# ── reading the file ──────────────────────────────────────────────────────────


def decode_csv(raw: bytes) -> str:
    """Decode an upload, tolerating the BOM Excel adds to a saved CSV."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("file is not valid UTF-8 text") from exc


def _cell(row: dict[Any, Any], header: str | None) -> str:
    """One cell as text.

    Defensive about ``DictReader``'s ragged-row behaviour: a short row yields ``None``
    and a long one collects the overflow under a ``None`` key as a list.
    """
    if header is None:
        return ""
    value = row.get(header)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value).strip()
    return str(value).strip()


def _resolve(headers: Sequence[str], name: str | None) -> str | None:
    """Match a mapping's column name against the file's actual headers."""
    if not name:
        return None
    wanted = normalise_header(name)
    for header in headers:
        if header and normalise_header(header) == wanted:
            return header
    return None


def read_csv(content: str) -> tuple[list[str], list[tuple[int, dict[Any, Any]]]]:
    """Header names and numbered data rows.

    Row numbers are the file's own line numbers, so an error message points at
    something the user can find in a text editor.
    """
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if not reader.fieldnames:
        raise CsvFormatError("file has no header row")

    headers = [h.strip() for h in reader.fieldnames]
    rows = [(reader.line_num, dict(row)) for row in reader]
    return headers, rows


# ── the plan ──────────────────────────────────────────────────────────────────


def _existing_content(
    session: Session, account_id: int, external_ids: Sequence[str]
) -> dict[str, tuple[dt.date, Decimal, str | None, str | None]]:
    """What the database already holds for these ids, for the create/update/skip call.

    Used only to *describe* the change. The write itself never branches on it — it is
    an unconditional upsert, so a row that appeared between this read and the write is
    handled by the unique index rather than by hoping the read was still true.
    """
    if not external_ids:
        return {}

    rows = session.execute(
        select(
            Transaction.external_id,
            Transaction.posted_at,
            Transaction.amount,
            Transaction.merchant,
            Transaction.description,
        ).where(
            Transaction.account_id == account_id,
            Transaction.external_id.in_(list(external_ids)),
        )
    ).all()

    return {
        str(external_id): (posted_at, amount, merchant, description)
        for external_id, posted_at, amount, merchant, description in rows
    }


def plan_import(
    session: Session, account_id: int, content: str, mapping: ColumnMapping
) -> ImportPlan:
    """Parse ``content`` under ``mapping`` and decide what each row would do.

    Reads. Never writes — this is what both the preview route and the commit route
    run, so the preview a user approves is literally the plan that gets executed.

    A row is ``update`` only when something the import owns actually differs.
    An unchanged row is ``skip``, which is what makes a second import of the same file
    report zeros rather than "412 updated" — the same outcome, but only one of the two
    tells you the import was a no-op.

    The import owns ``posted_at``, ``amount``, ``merchant`` and ``description`` and
    nothing else. A category a human set, or a transfer pairing, is not part of the
    comparison and is not part of the write: re-importing a file must never undo a
    decision somebody made in the app.
    """
    file_errors: list[str] = []

    headers, raw_rows = read_csv(content)
    date_column = _resolve(headers, mapping.posted_at)
    amount_column = _resolve(headers, mapping.amount)
    merchant_column = _resolve(headers, mapping.merchant)
    description_column = _resolve(headers, mapping.description)
    external_id_column = _resolve(headers, mapping.external_id)

    for label, name, column in (
        ("posted_at", mapping.posted_at, date_column),
        ("amount", mapping.amount, amount_column),
    ):
        if column is None:
            raise CsvFormatError(
                f"mapping names column {name!r} for {label}, which this file does not have"
            )

    if not raw_rows:
        raise CsvFormatError("file has a header but no data rows")

    date_values = [v for _, row in raw_rows if (v := _cell(row, date_column))]
    date_format = detect_date_format(date_values)
    if date_format is None:
        file_errors.append(
            "no supported date format matches this file's date column — re-export "
            "with ISO dates (YYYY-MM-DD) rather than have the import guess"
        )

    invert = bool(mapping.invert_amount)
    parsed: list[ParsedRow] = []
    occurrences: Counter[tuple[dt.date, Decimal, str]] = Counter()
    seen_ids: set[str] = set()

    for row_number, row in raw_rows:
        errors: list[str] = []

        posted_at: dt.date | None = None
        raw_date = _cell(row, date_column)
        if not raw_date:
            errors.append("date is empty")
        elif date_format is None:
            errors.append(f"date {raw_date!r} could not be parsed — no format fits this file")
        else:
            try:
                posted_at = parse_date(raw_date, date_format)
            except ValueError as exc:
                errors.append(str(exc))

        amount: Decimal | None = None
        try:
            amount = parse_amount(_cell(row, amount_column), invert=invert)
        except ValueError as exc:
            errors.append(str(exc))

        merchant = normalise_text(_cell(row, merchant_column))
        description = normalise_text(_cell(row, description_column))

        external_id: str | None = None
        if posted_at is not None and amount is not None and not errors:
            supplied = normalise_text(_cell(row, external_id_column))
            if supplied is not None:
                external_id = supplied
            else:
                key = group_key(posted_at, amount, merchant)
                external_id = derive_external_id(
                    account_id, posted_at, amount, merchant, description, occurrences[key]
                )
                occurrences[key] += 1

            if external_id in seen_ids:
                errors.append(
                    f"external id {external_id!r} appears more than once in this file; "
                    "only the first occurrence would be imported"
                )
                external_id = None
            else:
                seen_ids.add(external_id)

        parsed.append(
            ParsedRow(
                row_number=row_number,
                posted_at=posted_at,
                amount=amount,
                merchant=merchant,
                description=description,
                external_id=external_id,
                errors=tuple(errors),
            )
        )

    existing = _existing_content(
        session, account_id, [r.external_id for r in parsed if r.external_id is not None]
    )

    decided: list[ParsedRow] = []
    for candidate in parsed:
        if not candidate.is_valid or candidate.external_id is None:
            decided.append(candidate)
            continue

        previous = existing.get(candidate.external_id)
        if previous is None:
            action = CREATE
        elif previous == (
            candidate.posted_at,
            candidate.amount,
            candidate.merchant,
            candidate.description,
        ):
            action = SKIP
        else:
            action = UPDATE

        decided.append(
            ParsedRow(
                row_number=candidate.row_number,
                posted_at=candidate.posted_at,
                amount=candidate.amount,
                merchant=candidate.merchant,
                description=candidate.description,
                external_id=candidate.external_id,
                action=action,
                errors=candidate.errors,
            )
        )

    bad = sum(1 for decided_row in decided if decided_row.errors)
    if bad:
        file_errors.append(f"{bad} of {len(decided)} rows have errors and would be skipped")

    return ImportPlan(account_id=account_id, mapping=mapping, rows=decided, errors=file_errors)


def preview_import(session: Session, account_id: int, raw: bytes) -> ImportPlan:
    """The dry run behind ``POST /import/csv/preview``. Writes nothing.

    The mapping comes from whatever was saved against the account, falling back to
    detection from the header row. Preview's route signature carries no mapping, which
    is deliberate: the first look at a file should need no configuration, and the
    second one should need none either because the first commit saved it.
    """
    content = decode_csv(raw)
    saved = load_saved_mapping(session, account_id)
    if saved is not None:
        mapping = saved
    else:
        headers, _ = read_csv(content)
        mapping = detect_mapping(headers)

    return plan_import(session, account_id, content, mapping)


def commit_import(
    session: Session,
    account_id: int,
    content: str,
    mapping: ColumnMapping,
    save_as: str | None = None,
) -> ImportOutcome:
    """Apply an import. Idempotent by construction.

    Runs the same planner the preview does, so what a user approved is what executes
    — not a second implementation that agrees with the first until it doesn't.

    Every writable row is upserted on ``(account_id, external_id)`` regardless of what
    the plan decided. The counts come from the plan and are for the human; the write
    is unconditional, because branching on what an earlier read saw is the
    read-then-write race the unique index exists to eliminate. Re-importing the same
    file therefore changes nothing, which is the acceptance criterion.
    """
    plan = plan_import(session, account_id, content, mapping)

    rows = plan.writable
    if rows:
        session.execute(
            insert(Transaction)
            .values(
                [
                    {
                        "account_id": account_id,
                        "external_id": row.external_id,
                        "posted_at": row.posted_at,
                        "amount": row.amount,
                        "merchant": row.merchant,
                        "description": row.description,
                    }
                    for row in rows
                ]
            )
            .on_conflict_do_update(
                index_elements=[Transaction.account_id, Transaction.external_id],
                index_where=Transaction.external_id.isnot(None),
                set_={
                    "posted_at": text("excluded.posted_at"),
                    "amount": text("excluded.amount"),
                    "merchant": text("excluded.merchant"),
                    "description": text("excluded.description"),
                },
            )
        )
        session.flush()

    if save_as:
        save_mapping(session, account_id, save_as, mapping)

    return ImportOutcome(
        created=plan.count(CREATE),
        updated=plan.count(UPDATE),
        # Rows that parsed but matched an identical existing row, plus rows that
        # could not be parsed at all. Both were "not applied" from the user's side.
        skipped=plan.count(SKIP) + sum(1 for row in plan.rows if not row.is_valid),
        errors=list(plan.errors),
    )
