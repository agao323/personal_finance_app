"""Import the spreadsheet's net worth history into `balance_snapshots`.

A one-off, run once against the real export in `data/`, then kept because "one-off"
scripts get run again.

**This script is written against the header shape, never the values.** The export
never leaves `data/`, and no balance from it is ever read into a session's context —
see docs/SECURITY.md#handling-real-data-during-development. Everything here is tested
against a synthetic fixture with the same column layout.

Three properties worth stating, because each has a plausible wrong version:

**It writes through `services/balances.record_balance`.** That upsert is what makes a
re-run safe, and it is the only place a snapshot is written anywhere in the app.
Inserting directly would be faster and would quietly acquire a second, divergent way to
record a balance.

**The reconciliation report is the point, not a nicety.** An import that ran without
error and mapped one column to the wrong account produces a complete, plausible,
entirely wrong history — and nothing downstream would look broken. The report compares
what this script computed against the sheet's own total, per date.

**Ambiguous dates are rejected, not guessed.** `01/02/2026` is two different dates and
picking the wrong one shifts a year of history by eleven months, invisibly.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.account import Account
from app.models.enums import AccountKind, DataSource
from app.services.balances import record_balance
from app.services.net_worth import net_worth

#: Tried in order when the mapping declares no `date_format`. Deliberately excludes
#: every layout where the day and month could swap — see the module docstring.
UNAMBIGUOUS_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%b %d, %Y", "%d %B %Y")

#: A cent. Two figures that differ by less than this are the same figure; anything
#: larger is a mapping error worth a human looking at it.
TOLERANCE = Decimal("0.01")


class SheetImportError(Exception):
    """Something about the file or the mapping is wrong. The message says what."""


# ── mapping ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mapping:
    date_column: str
    total_column: str | None
    date_format: str | None
    #: sheet column → account name
    columns: dict[str, str]


def load_mapping(path: Path) -> Mapping:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SheetImportError(f"No mapping file at {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise SheetImportError(f"{path} is not valid TOML: {error}") from error

    sheet = raw.get("sheet", {})
    columns = raw.get("columns", {})

    if not columns:
        raise SheetImportError(f"{path} maps no columns — nothing would be imported")
    if not sheet.get("date_column"):
        raise SheetImportError(f"{path} does not name a date_column")

    # A mapping is names on both sides. A number here means someone pasted a value out
    # of the real sheet into a committed file.
    for column, account in columns.items():
        if not isinstance(account, str) or not account.strip():
            raise SheetImportError(f"column {column!r} maps to {account!r}, which is not a name")

    return Mapping(
        date_column=str(sheet["date_column"]),
        total_column=str(sheet["total_column"]) if sheet.get("total_column") else None,
        date_format=str(sheet["date_format"]) if sheet.get("date_format") else None,
        columns={str(k): str(v) for k, v in columns.items()},
    )


def unmapped_columns(headers: Sequence[str], mapping: Mapping) -> list[str]:
    """Columns in the file that the mapping ignores.

    Surfaced by the dry run rather than dropped in silence: an account nobody mapped
    is missing from every net worth figure this import produces, and the only clue
    would be a total that reads slightly low.
    """
    known = {mapping.date_column, *(mapping.total_column,), *mapping.columns}
    return [header for header in headers if header and header not in known]


def missing_columns(headers: Sequence[str], mapping: Mapping) -> list[str]:
    """Columns the mapping names that the file does not have — usually a typo."""
    present = set(headers)
    wanted = [mapping.date_column, *mapping.columns]
    if mapping.total_column:
        wanted.append(mapping.total_column)
    return [column for column in wanted if column not in present]


# ── parsing ───────────────────────────────────────────────────────────────────


def parse_amount(raw: str) -> Decimal | None:
    """A spreadsheet cell as a Decimal. Blank is None, which is not zero.

    A blank cell means the account did not exist yet, or was not tracked that month.
    Recording it as zero would claim the balance *was* zero, which is a different and
    much worse statement — it drags net worth down for every date before the account
    opened.

    Parentheses are accounting notation for a negative, which spreadsheets emit and
    nothing else in this codebase has to handle.
    """
    # The NO-BREAK SPACE is spelled out rather than pasted: several locales use it
    # as a thousands separator and spreadsheets export it verbatim, so stripping it
    # is wanted — but an invisible character in a string literal is a thing nobody
    # can review. Ordinary spaces go too.
    text = raw.strip().replace("$", "").replace(",", "").replace("\u00a0", "").replace(" ", "")
    if not text or text in {"-", "—", "N/A", "n/a"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()

    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise SheetImportError(f"Could not read {raw!r} as an amount") from error

    return -value if negative else value


def detect_date_format(values: Iterable[str], declared: str | None = None) -> str:
    """The one format that parses every date in the file.

    Every date, not the first: a file whose first rows are unambiguous and whose later
    ones are not would otherwise be read with a format that fails halfway through — or
    worse, silently succeeds with the wrong reading.
    """
    samples = [value.strip() for value in values if value.strip()]
    if not samples:
        raise SheetImportError("The file has no dates")

    candidates = [declared] if declared else list(UNAMBIGUOUS_DATE_FORMATS)
    for candidate in candidates:
        assert candidate is not None
        try:
            for sample in samples:
                dt.datetime.strptime(sample, candidate)
        except ValueError:
            continue
        return candidate

    raise SheetImportError(
        f"No unambiguous date format parses every row (first is {samples[0]!r}). "
        "Set date_format in the mapping — and if the file uses a day/month layout, "
        "say so explicitly rather than letting this guess."
    )


@dataclass
class SheetRow:
    as_of: dt.date
    #: account name → balance, for the columns that had a value
    balances: dict[str, Decimal]
    sheet_total: Decimal | None


def read_sheet(path: Path, mapping: Mapping) -> tuple[list[SheetRow], list[str]]:
    """Parse the export. Returns the rows and the columns nobody mapped."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as error:
        raise SheetImportError(f"No export at {path}") from error

    reader = csv.DictReader(text.splitlines())
    headers = reader.fieldnames or []
    if not headers:
        raise SheetImportError(f"{path} has no header row")

    absent = missing_columns(headers, mapping)
    if absent:
        raise SheetImportError(f"The mapping names columns the file does not have: {absent}")

    raw_rows = list(reader)
    if not raw_rows:
        raise SheetImportError(f"{path} has a header and no rows")

    date_format = detect_date_format(
        (row.get(mapping.date_column) or "" for row in raw_rows), mapping.date_format
    )

    rows: list[SheetRow] = []
    for number, raw in enumerate(raw_rows, start=2):
        raw_date = (raw.get(mapping.date_column) or "").strip()
        if not raw_date:
            continue
        try:
            as_of = dt.datetime.strptime(raw_date, date_format).date()
        except ValueError as error:
            raise SheetImportError(f"row {number}: could not read date {raw_date!r}") from error

        balances: dict[str, Decimal] = {}
        for column, account_name in mapping.columns.items():
            try:
                value = parse_amount(raw.get(column) or "")
            except SheetImportError as error:
                raise SheetImportError(f"row {number}, column {column!r}: {error}") from error
            if value is not None:
                balances[account_name] = value

        total = None
        if mapping.total_column:
            total = parse_amount(raw.get(mapping.total_column) or "")

        rows.append(SheetRow(as_of=as_of, balances=balances, sheet_total=total))

    return rows, unmapped_columns(headers, mapping)


# ── reconciliation ────────────────────────────────────────────────────────────


@dataclass
class Reconciliation:
    as_of: dt.date
    sheet_total: Decimal | None
    #: Assets minus liabilities from the values this import read, unadjusted.
    raw_total: Decimal
    #: What the app will actually show: ownership-adjusted, from the database.
    adjusted_total: Decimal | None = None

    @property
    def difference(self) -> Decimal | None:
        if self.sheet_total is None:
            return None
        return self.raw_total - self.sheet_total

    @property
    def matches(self) -> bool:
        difference = self.difference
        return difference is None or abs(difference) < TOLERANCE


def raw_total_for(row: SheetRow, kinds: dict[str, AccountKind]) -> Decimal:
    """Assets minus liabilities, from the sheet's own numbers.

    Liabilities are stored positive and subtracted — the same convention as the rest
    of the app, so a mortgage column of 295800 means owing that much.
    """
    total = Decimal("0.00")
    for account_name, value in row.balances.items():
        kind = kinds.get(account_name)
        if kind is AccountKind.LIABILITY:
            total -= value
        else:
            total += value
    return total


def reconcile(rows: Sequence[SheetRow], kinds: dict[str, AccountKind]) -> list[Reconciliation]:
    """Compare what this import read against the sheet's own total, per date.

    This is the check that catches a column mapped to the wrong account. Such an
    import runs cleanly and produces a complete, plausible, entirely wrong history —
    the totals are the only thing that disagrees.

    The comparison is deliberately against the **raw** sum rather than the
    ownership-adjusted figure. A spreadsheet almost certainly does not model fractional
    ownership, so comparing against the adjusted number would flag every part-owned
    account as a mismatch and bury the real ones. The adjusted figure is reported
    alongside, for information.
    """
    return [
        Reconciliation(
            as_of=row.as_of, sheet_total=row.sheet_total, raw_total=raw_total_for(row, kinds)
        )
        for row in rows
    ]


# ── the run ───────────────────────────────────────────────────────────────────


@dataclass
class Outcome:
    rows: int = 0
    snapshots_written: int = 0
    accounts_touched: set[str] = field(default_factory=set)
    unknown_accounts: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    mismatches: list[Reconciliation] = field(default_factory=list)
    reconciliation: list[Reconciliation] = field(default_factory=list)

    @property
    def dates(self) -> tuple[dt.date, dt.date] | None:
        if not self.reconciliation:
            return None
        days = [item.as_of for item in self.reconciliation]
        return min(days), max(days)


def account_index(session: Session) -> dict[str, Account]:
    return {account.name: account for account in session.execute(select(Account)).scalars()}


def run(
    session: Session,
    export: Path,
    mapping_path: Path,
    *,
    dry_run: bool = True,
    viewer_id: int | None = None,
) -> Outcome:
    """Import, or say what importing would do.

    `dry_run` writes nothing at all — no snapshot, no flush. It is the default because
    the first run of this against a real export should never be the one that writes.
    """
    mapping = load_mapping(mapping_path)
    rows, unmapped = read_sheet(export, mapping)
    accounts = account_index(session)

    outcome = Outcome(rows=len(rows), unmapped=unmapped)

    wanted = set(mapping.columns.values())
    outcome.unknown_accounts = sorted(name for name in wanted if name not in accounts)
    if outcome.unknown_accounts:
        raise SheetImportError(
            "The mapping names accounts that do not exist: "
            f"{outcome.unknown_accounts}. Create them first — this script records "
            "balances, it does not invent accounts."
        )

    kinds = {name: accounts[name].kind for name in wanted}
    outcome.reconciliation = reconcile(rows, kinds)
    outcome.mismatches = [item for item in outcome.reconciliation if not item.matches]

    if dry_run:
        return outcome

    for row in rows:
        for account_name, value in row.balances.items():
            record_balance(
                session,
                account_id=accounts[account_name].id,
                as_of=row.as_of,
                balance=value,
                source=DataSource.MANUAL,
            )
            outcome.snapshots_written += 1
            outcome.accounts_touched.add(account_name)

    session.flush()

    # Only now can the adjusted figure be computed — it comes from the database, not
    # from the file, and that is the point: it is what the app will actually show.
    for item in outcome.reconciliation:
        item.adjusted_total = net_worth(session, as_of=item.as_of, viewer_id=viewer_id).net_worth

    return outcome


def report(outcome: Outcome, *, dry_run: bool) -> str:
    """The reconciliation report, as text. Amounts are the caller's own data."""
    lines: list[str] = []
    span = outcome.dates
    lines.append("DRY RUN — nothing was written" if dry_run else "Imported")
    lines.append(f"  rows:      {outcome.rows}")
    if span:
        lines.append(f"  dates:     {span[0]} to {span[1]}")
    if not dry_run:
        lines.append(f"  snapshots: {outcome.snapshots_written}")
        lines.append(f"  accounts:  {len(outcome.accounts_touched)}")

    if outcome.unmapped:
        lines.append("")
        lines.append(f"  Columns not mapped, and therefore ignored: {outcome.unmapped}")
        lines.append("  If any of those is an account, it is missing from every figure below.")

    lines.append("")
    if not any(item.sheet_total is not None for item in outcome.reconciliation):
        lines.append("  No total column in the mapping, so the parse could not be checked.")
        lines.append("  Set sheet.total_column — an unchecked import is a plausible wrong one.")
    elif outcome.mismatches:
        lines.append(f"  {len(outcome.mismatches)} dates disagree with the sheet's own total:")
        for item in outcome.mismatches[:20]:
            lines.append(
                f"    {item.as_of}  sheet {item.sheet_total}  imported {item.raw_total}  "
                f"off by {item.difference}"
            )
        if len(outcome.mismatches) > 20:
            lines.append(f"    … and {len(outcome.mismatches) - 20} more")
        lines.append("")
        lines.append("  A disagreement is usually a column mapped to the wrong account.")
    else:
        lines.append(f"  All {len(outcome.reconciliation)} dates match the sheet's own total.")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="CSV exported from the spreadsheet, in data/")
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("config/sheet_mapping.toml"),
        help="column → account mapping (default: config/sheet_mapping.toml)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="actually record the snapshots. Without this, nothing is written.",
    )
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    url = args.database_url or get_settings().database_url
    engine = create_engine(url, connect_args={"prepare_threshold": None})

    try:
        with Session(engine) as session:
            outcome = run(session, args.export, args.mapping, dry_run=not args.write)
            print(report(outcome, dry_run=not args.write))

            if args.write and outcome.mismatches:
                # Committed anyway: the snapshots are correct readings of the file,
                # and rolling back would mean fixing the mapping with nothing to
                # compare against. Re-running after a correction overwrites them.
                print(
                    "\n  Committed with mismatches. Fix the mapping and re-run — it is idempotent."
                )
            if args.write:
                session.commit()
    except SheetImportError as error:
        print(f"import_sheet_history: {error}", file=sys.stderr)
        return 1

    return 1 if outcome.mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
