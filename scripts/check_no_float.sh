#!/usr/bin/env bash
#
# Fail if a SQLAlchemy column uses an approximate numeric type.
#
# Money is Decimal in Python and NUMERIC(19,2) in Postgres. A Float column stores
# 0.1 + 0.2 as 0.30000000000000004, and the corruption is silent — balances drift by
# fractions of a cent and totals stop matching the rows that make them up. There is
# no error to notice, which is exactly why this needs a guard rather than a code
# review habit.
#
# Usage: check_no_float.sh [directory]   (default: api/app)

set -euo pipefail

target="${1:-api/app}"

if [[ ! -d "$target" ]]; then
  echo "check_no_float: no such directory: $target" >&2
  exit 2
fi

# Matches the SQLAlchemy spellings of approximate numerics as they appear in a
# column definition — Float, REAL, DOUBLE_PRECISION — and the raw Python float type
# used as a mapped annotation.
pattern='(Column|mapped_column)\([^)]*\b(Float|REAL|DOUBLE_PRECISION)\b|Mapped\[float\]'

if matches=$(grep -rEn --include='*.py' "$pattern" "$target" 2>/dev/null); then
  echo "check_no_float: approximate numeric type in a column definition." >&2
  echo "" >&2
  echo "$matches" >&2
  echo "" >&2
  echo "Money is Decimal / NUMERIC(19,2). See docs/ARCHITECTURE.md#money." >&2
  exit 1
fi

echo "check_no_float: ok ($target)"
