"""Rebuild `app/services/analysis/returns.csv` from Damodaran's historical returns workbook.

The projections (plan 117) run on annual **real** returns by asset class from a committed table;
nothing is fetched at runtime. This script turns the public workbook into that table, so the
table can be rebuilt when the workbook is updated each January:

    curl -sSLO https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls
    cd api && uv run --with xlrd python scripts/build_returns.py ../histretSP.xls

`xlrd` is not a project dependency: it reads the legacy `.xls` format for this one job and is
never imported by the app. The workbook is not committed; the table is.

Columns are found by their headers on the "Returns by year" sheet, under "Annual Real Returns",
and the script refuses a workbook whose headers have moved rather than read the wrong column.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import xlrd  # type: ignore[import-untyped,import-not-found,unused-ignore]

OUT = Path(__file__).resolve().parents[1] / "app" / "services" / "analysis" / "returns.csv"
SHEET = "Returns by year"
HEADER_ROW = 19
GROUP_ROW = 18
#: Each asset class and the workbook column it comes from, matched by header prefix within the
#: "Annual Real Returns" group. International stocks have no series here, so they are the S&P
#: 500 — a proxy, named in the file's header.
COLUMNS = {
    "us_equity": "S&P 500",
    "intl_equity": "S&P 500",
    "bonds": "!0-year T.Bonds",  # sic: the workbook's own header
    "cash": "3-month T. Bill",
    "real_estate": "Real Estate",
    "other": "Gold",
}
CLASSES = ("us_equity", "intl_equity", "bonds", "cash", "real_estate", "other")

SOURCE = (
    'Aswath Damodaran, "Historical Returns on Stocks, Bonds and Bills", NYU Stern, '
    'histretSP.xls ("Returns by year", Annual Real Returns), '
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histret.html"
)
LICENCE = (
    "no formal licence; the author's usage rules "
    "(https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datahistory.html#rules) welcome use, "
    "ask no attribution, and exclude legal proceedings and policy debates. Attributed here anyway"
)
MAPPING = (
    "us_equity S&P 500 with dividends; intl_equity S&P 500 (a proxy: the workbook has no "
    "international series); bonds US 10-year Treasury; cash 3-month T-bill; real_estate US home "
    "prices; other gold"
)
UNITS = (
    "annual real returns as decimal fractions (0.05 is 5%), rounded to six places; rebuilt by "
    "api/scripts/build_returns.py"
)


def columns(sheet: xlrd.sheet.Sheet) -> dict[str, int]:
    """Each class's column index, from the headers in the "Annual Real Returns" group."""
    start = next(
        c
        for c in range(sheet.ncols)
        if "Annual Real Returns" in str(sheet.cell_value(GROUP_ROW, c))
    )
    end = next(
        (c for c in range(start + 1, sheet.ncols) if str(sheet.cell_value(GROUP_ROW, c)).strip()),
        sheet.ncols,
    )
    found: dict[str, int] = {}
    for cls, prefix in COLUMNS.items():
        matches = [
            c
            for c in range(start, end)
            if str(sheet.cell_value(HEADER_ROW, c)).strip().startswith(prefix)
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"{cls}: expected one '{prefix}' column under real returns, got {matches}"
            )
        found[cls] = matches[0]
    return found


def main(path: str) -> None:
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_name(SHEET)
    where = columns(sheet)
    lines: list[str] = []
    years: list[int] = []
    for row in range(HEADER_ROW + 1, sheet.nrows):
        year = sheet.cell_value(row, 0)
        if not isinstance(year, float) or not 1900 < year < 2100:
            break
        values = [sheet.cell_value(row, where[cls]) for cls in CLASSES]
        if not all(isinstance(v, float) for v in values):
            raise SystemExit(f"{int(year)}: a return is missing")
        years.append(int(year))
        lines.append(f"{int(year)}," + ",".join(f"{v:.6f}" for v in values))
    if years != list(range(years[0], years[-1] + 1)):
        raise SystemExit("the years are not contiguous")
    header = "".join(
        [
            f"# source: {SOURCE} - retrieved {dt.date.today().isoformat()}, "
            f"covering {years[0]} to {years[-1]}\n",
            f"# licence: {LICENCE}\n",
            f"# mapping: {MAPPING}\n",
            f"# units: {UNITS}\n",
            f"year,{','.join(CLASSES)}\n",
        ]
    )
    OUT.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {years[0]} to {years[-1]}, {len(years)} years")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
