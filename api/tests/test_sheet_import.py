"""Tests for the spreadsheet history import.

Every fixture here is invented. The real export never leaves `data/` and none of its
values are ever read into a session — what these test is the **header shape** and the
decisions the script makes about it, which is all that needs testing.

The reconciliation tests are the ones that matter. An import that maps a column to the
wrong account runs cleanly and produces a complete, plausible, entirely wrong history;
the totals are the only thing that disagrees.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import AccountKind
from scripts.import_sheet_history import (
    SheetImportError,
    SheetRow,
    detect_date_format,
    load_mapping,
    missing_columns,
    parse_amount,
    raw_total_for,
    reconcile,
    report,
    run,
    unmapped_columns,
)

HEADERS = "Date,Checking,Savings,Mortgage,Net Worth\n"
SHEET = HEADERS + (
    "2026-01-01,1000.00,5000.00,100000.00,-94000.00\n"
    "2026-02-01,1100.00,5100.00,99000.00,-92800.00\n"
)

MAPPING = """
[sheet]
date_column = "Date"
total_column = "Net Worth"

[columns]
"Checking" = "Checking"
"Savings" = "Savings"
"Mortgage" = "Mortgage"
"""


@pytest.fixture
def sheet(tmp_path: Path) -> Path:
    path = tmp_path / "history.csv"
    path.write_text(SHEET, encoding="utf-8")
    return path


@pytest.fixture
def mapping_file(tmp_path: Path) -> Path:
    path = tmp_path / "mapping.toml"
    path.write_text(MAPPING, encoding="utf-8")
    return path


@pytest.fixture
def accounts(db_session: Session, make_account: Callable[..., int]) -> dict[str, int]:
    """Three accounts matching the fixture's columns, each fully owned."""
    ids = {
        "Checking": make_account("Checking", kind="liquid_asset", subtype="checking"),
        "Savings": make_account("Savings", kind="liquid_asset", subtype="savings"),
        "Mortgage": make_account("Mortgage", kind="liability", subtype="mortgage"),
    }
    owner_id = db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
    for account_id in ids.values():
        db_session.execute(
            text(
                "INSERT INTO ownership_stakes "
                "(account_id, owner_user_id, percentage, effective_from) "
                "VALUES (:a, :u, 100.00, :d)"
            ),
            {"a": account_id, "u": owner_id, "d": dt.date(2020, 1, 1)},
        )
    db_session.flush()
    return ids


# ── the mapping file ──────────────────────────────────────────────────────────


def test_reads_a_mapping(mapping_file: Path) -> None:
    mapping = load_mapping(mapping_file)

    assert mapping.date_column == "Date"
    assert mapping.total_column == "Net Worth"
    assert mapping.columns["Mortgage"] == "Mortgage"


def test_rejects_a_mapping_with_no_columns(tmp_path: Path) -> None:
    path = tmp_path / "empty.toml"
    path.write_text('[sheet]\ndate_column = "Date"\n', encoding="utf-8")

    with pytest.raises(SheetImportError, match="maps no columns"):
        load_mapping(path)


def test_rejects_a_mapping_with_no_date_column(tmp_path: Path) -> None:
    path = tmp_path / "nodate.toml"
    path.write_text('[columns]\n"Checking" = "Checking"\n', encoding="utf-8")

    with pytest.raises(SheetImportError, match="date_column"):
        load_mapping(path)


def test_rejects_a_number_where_an_account_name_belongs(tmp_path: Path) -> None:
    """A number here means someone pasted a value out of the real sheet.

    This file is committed and `data/` is not, so that is the one mistake worth
    refusing outright rather than tolerating.
    """
    path = tmp_path / "bad.toml"
    path.write_text(
        '[sheet]\ndate_column = "Date"\n[columns]\n"Checking" = 1234.56\n', encoding="utf-8"
    )

    with pytest.raises(SheetImportError, match="not a name"):
        load_mapping(path)


def test_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SheetImportError, match="No mapping file"):
        load_mapping(tmp_path / "absent.toml")


# ── column matching ───────────────────────────────────────────────────────────


def test_names_columns_nobody_mapped(mapping_file: Path) -> None:
    """An unmapped account is missing from every figure, and the only clue would be a
    total that reads slightly low."""
    mapping = load_mapping(mapping_file)

    assert unmapped_columns(["Date", "Checking", "Brokerage", "Net Worth"], mapping) == [
        "Brokerage"
    ]


def test_names_mapped_columns_the_file_does_not_have(mapping_file: Path) -> None:
    mapping = load_mapping(mapping_file)

    assert missing_columns(["Date", "Checking", "Net Worth"], mapping) == ["Savings", "Mortgage"]


# ── amounts ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        (" 1234.56 ", Decimal("1234.56")),
        ("(500.00)", Decimal("-500.00")),
        ("-500.00", Decimal("-500.00")),
        ("0", Decimal("0")),
    ],
)
def test_parses_the_shapes_a_spreadsheet_emits(raw: str, expected: Decimal) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "-", "—", "N/A"])
def test_a_blank_cell_is_not_zero(raw: str) -> None:
    """Blank means the account did not exist yet, or was not tracked that month.

    Zero would claim the balance *was* zero, which drags net worth down for every date
    before the account opened.
    """
    assert parse_amount(raw) is None


def test_refuses_a_cell_it_cannot_read() -> None:
    with pytest.raises(SheetImportError, match="Could not read"):
        parse_amount("about five thousand")


# ── dates ─────────────────────────────────────────────────────────────────────


def test_detects_an_unambiguous_format() -> None:
    assert detect_date_format(["2026-01-01", "2026-02-01"]) == "%Y-%m-%d"


def test_refuses_an_ambiguous_layout() -> None:
    """01/02/2026 is two different dates, and picking wrong shifts a year of history
    by eleven months, invisibly."""
    with pytest.raises(SheetImportError, match="No unambiguous date format"):
        detect_date_format(["01/02/2026", "03/04/2026"])


def test_an_explicit_format_is_honoured() -> None:
    assert detect_date_format(["01/02/2026"], declared="%d/%m/%Y") == "%d/%m/%Y"


def test_requires_a_format_that_parses_every_row() -> None:
    """Not just the first: a file that starts unambiguous and turns ambiguous would
    otherwise be read with a format that fails — or silently succeeds — halfway."""
    with pytest.raises(SheetImportError):
        detect_date_format(["2026-01-01", "not a date"])


# ── reconciliation ────────────────────────────────────────────────────────────

KINDS = {
    "Checking": AccountKind.LIQUID_ASSET,
    "Savings": AccountKind.LIQUID_ASSET,
    "Mortgage": AccountKind.LIABILITY,
}


def test_liabilities_are_subtracted() -> None:
    """Stored positive, subtracted — the same convention as the rest of the app."""
    row = SheetRow(
        as_of=dt.date(2026, 1, 1),
        balances={"Checking": Decimal("1000"), "Mortgage": Decimal("100000")},
        sheet_total=None,
    )

    assert raw_total_for(row, KINDS) == Decimal("-99000")


def test_a_matching_total_reconciles() -> None:
    row = SheetRow(
        as_of=dt.date(2026, 1, 1),
        balances={
            "Checking": Decimal("1000"),
            "Savings": Decimal("5000"),
            "Mortgage": Decimal("100000"),
        },
        sheet_total=Decimal("-94000.00"),
    )

    assert reconcile([row], KINDS)[0].matches is True


def test_a_mismatch_is_flagged_with_the_difference() -> None:
    """The check that catches a column mapped to the wrong account."""
    row = SheetRow(
        as_of=dt.date(2026, 1, 1),
        balances={"Checking": Decimal("1000")},
        sheet_total=Decimal("-94000.00"),
    )

    result = reconcile([row], KINDS)[0]

    assert result.matches is False
    assert result.difference == Decimal("95000.00")


def test_a_sub_cent_difference_is_not_a_mismatch() -> None:
    """Spreadsheets round for display. A tenth of a cent is not a mapping error."""
    row = SheetRow(
        as_of=dt.date(2026, 1, 1),
        balances={"Checking": Decimal("1000.004")},
        sheet_total=Decimal("1000.00"),
    )

    assert reconcile([row], KINDS)[0].matches is True


# ── the run ───────────────────────────────────────────────────────────────────


def test_a_dry_run_writes_nothing(
    db_session: Session, sheet: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    """The default, because the first run against a real export should never write."""
    before = db_session.execute(text("SELECT count(*) FROM balance_snapshots")).scalar_one()

    outcome = run(db_session, sheet, mapping_file, dry_run=True)

    after = db_session.execute(text("SELECT count(*) FROM balance_snapshots")).scalar_one()
    assert (before, after) == (after, before)
    assert outcome.rows == 2
    assert outcome.dates == (dt.date(2026, 1, 1), dt.date(2026, 2, 1))


def test_writing_records_a_snapshot_per_account_per_date(
    db_session: Session, sheet: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    outcome = run(db_session, sheet, mapping_file, dry_run=False)

    assert outcome.snapshots_written == 6
    stored = db_session.execute(
        text("SELECT balance FROM balance_snapshots WHERE account_id = :a AND as_of = :d"),
        {"a": accounts["Checking"], "d": dt.date(2026, 2, 1)},
    ).scalar_one()
    assert stored == Decimal("1100.00")


def test_re_running_is_idempotent(
    db_session: Session, sheet: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    """Safe to re-run while the mapping is being corrected — which is the whole point,
    since correcting it is exactly what the reconciliation report prompts."""
    run(db_session, sheet, mapping_file, dry_run=False)
    first = db_session.execute(text("SELECT count(*) FROM balance_snapshots")).scalar_one()

    run(db_session, sheet, mapping_file, dry_run=False)

    assert db_session.execute(text("SELECT count(*) FROM balance_snapshots")).scalar_one() == first


def test_a_corrected_value_replaces_the_old_one(
    db_session: Session, tmp_path: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    original = tmp_path / "a.csv"
    original.write_text(
        HEADERS + "2026-01-01,1000.00,5000.00,100000.00,-94000.00\n", encoding="utf-8"
    )
    run(db_session, original, mapping_file, dry_run=False)

    corrected = tmp_path / "b.csv"
    corrected.write_text(
        HEADERS + "2026-01-01,2000.00,5000.00,100000.00,-93000.00\n", encoding="utf-8"
    )
    run(db_session, corrected, mapping_file, dry_run=False)

    stored = db_session.execute(
        text("SELECT balance FROM balance_snapshots WHERE account_id = :a AND as_of = :d"),
        {"a": accounts["Checking"], "d": dt.date(2026, 1, 1)},
    ).scalar_one()
    assert stored == Decimal("2000.00")


def test_the_report_flags_a_deliberately_wrong_total(
    db_session: Session, tmp_path: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    """The acceptance criterion with teeth.

    This file's own total disagrees with its columns — which is what a column mapped
    to the wrong account looks like from the outside.
    """
    broken = tmp_path / "broken.csv"
    broken.write_text(
        HEADERS + "2026-01-01,1000.00,5000.00,100000.00,-11111.11\n", encoding="utf-8"
    )

    outcome = run(db_session, broken, mapping_file, dry_run=True)

    assert len(outcome.mismatches) == 1
    assert outcome.mismatches[0].as_of == dt.date(2026, 1, 1)
    text_report = report(outcome, dry_run=True)
    assert "disagree with the sheet's own total" in text_report
    assert "wrong account" in text_report


def test_the_report_says_when_it_had_nothing_to_check_against(
    db_session: Session, sheet: Path, tmp_path: Path, accounts: dict[str, int]
) -> None:
    """An import with no total column ran, and proved nothing."""
    no_total = tmp_path / "no_total.toml"
    no_total.write_text(
        '[sheet]\ndate_column = "Date"\n[columns]\n"Checking" = "Checking"\n', encoding="utf-8"
    )

    outcome = run(db_session, sheet, no_total, dry_run=True)

    assert "could not be checked" in report(outcome, dry_run=True)


def test_the_report_names_unmapped_columns(
    db_session: Session, sheet: Path, tmp_path: Path, accounts: dict[str, int]
) -> None:
    partial = tmp_path / "partial.toml"
    partial.write_text(
        '[sheet]\ndate_column = "Date"\ntotal_column = "Net Worth"\n'
        '[columns]\n"Checking" = "Checking"\n',
        encoding="utf-8",
    )

    outcome = run(db_session, sheet, partial, dry_run=True)

    assert set(outcome.unmapped) == {"Savings", "Mortgage"}
    assert "not mapped" in report(outcome, dry_run=True)


def test_refuses_a_mapping_naming_an_account_that_does_not_exist(
    db_session: Session, sheet: Path, tmp_path: Path
) -> None:
    """This script records balances; it does not invent accounts."""
    ghost = tmp_path / "ghost.toml"
    ghost.write_text(
        '[sheet]\ndate_column = "Date"\n[columns]\n"Checking" = "No Such Account"\n',
        encoding="utf-8",
    )

    with pytest.raises(SheetImportError, match="do not exist"):
        run(db_session, sheet, ghost, dry_run=True)


def test_reports_the_adjusted_total_after_writing(
    db_session: Session, sheet: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    """The figure the app will actually show, read back from the database.

    Fully owned here, so it equals the raw total — the point is that it comes from
    `services/net_worth` rather than from the file.
    """
    outcome = run(db_session, sheet, mapping_file, dry_run=False)

    first = outcome.reconciliation[0]
    assert first.adjusted_total == Decimal("-94000.00")


def test_a_part_owned_account_makes_the_adjusted_total_differ(
    db_session: Session,
    sheet: Path,
    mapping_file: Path,
    accounts: dict[str, int],
) -> None:
    """Which is why reconciliation compares against the raw sum, not this one.

    A spreadsheet does not model fractional ownership, so comparing the adjusted
    figure against the sheet's total would flag every part-owned account and bury the
    real mismatches.
    """
    db_session.execute(
        text("UPDATE ownership_stakes SET percentage = 50.00 WHERE account_id = :a"),
        {"a": accounts["Savings"]},
    )

    outcome = run(db_session, sheet, mapping_file, dry_run=False)

    first = outcome.reconciliation[0]
    assert first.matches is True
    assert first.adjusted_total != first.raw_total


def test_rejects_a_file_with_only_a_header(
    db_session: Session, tmp_path: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text(HEADERS, encoding="utf-8")

    with pytest.raises(SheetImportError, match="no rows"):
        run(db_session, empty, mapping_file, dry_run=True)


def test_rejects_a_file_missing_a_mapped_column(
    db_session: Session, tmp_path: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    short = tmp_path / "short.csv"
    short.write_text("Date,Checking,Net Worth\n2026-01-01,1000.00,1000.00\n", encoding="utf-8")

    with pytest.raises(SheetImportError, match="does not have"):
        run(db_session, short, mapping_file, dry_run=True)


def test_a_blank_cell_records_no_snapshot(
    db_session: Session, tmp_path: Path, mapping_file: Path, accounts: dict[str, int]
) -> None:
    """Rather than a zero balance, which would be a claim nobody made."""
    gappy = tmp_path / "gappy.csv"
    gappy.write_text(HEADERS + "2026-01-01,1000.00,,100000.00,-99000.00\n", encoding="utf-8")

    run(db_session, gappy, mapping_file, dry_run=False)

    recorded = db_session.execute(
        text("SELECT count(*) FROM balance_snapshots WHERE account_id = :a"),
        {"a": accounts["Savings"]},
    ).scalar_one()
    assert recorded == 0
