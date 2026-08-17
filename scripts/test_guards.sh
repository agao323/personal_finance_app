#!/usr/bin/env bash
#
# Tests for the guard scripts.
#
# A guard that never fires is indistinguishable from a broken guard, and this is the
# only thing that tells the two apart. Each guard is run against a violating fixture
# (must fail) and a clean one (must pass).

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

passed=0
failed=0

expect() {
  local want="$1" name="$2"
  shift 2
  local out
  out=$("$@" 2>&1)
  local got=$?
  if [[ $got -eq $want ]]; then
    echo "  ok    $name"
    passed=$((passed + 1))
  else
    echo "  FAIL  $name (expected exit $want, got $got)"
    echo "$out" | sed 's/^/          /'
    failed=$((failed + 1))
  fi
}

# ── check_no_float ────────────────────────────────────────────────────────────
echo "check_no_float.sh"

mkdir -p "$work/float_dirty"
cat >"$work/float_dirty/model.py" <<'PY'
from sqlalchemy import Column, Float
balance = Column(Float, nullable=False)
PY
expect 1 "fails on Column(Float)" "$here/check_no_float.sh" "$work/float_dirty"

mkdir -p "$work/float_dirty2"
cat >"$work/float_dirty2/model.py" <<'PY'
from sqlalchemy.orm import Mapped, mapped_column
balance: Mapped[float] = mapped_column()
PY
expect 1 "fails on Mapped[float]" "$here/check_no_float.sh" "$work/float_dirty2"

mkdir -p "$work/float_dirty3"
cat >"$work/float_dirty3/model.py" <<'PY'
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION
rate = Column(DOUBLE_PRECISION)
PY
expect 1 "fails on DOUBLE_PRECISION" "$here/check_no_float.sh" "$work/float_dirty3"

mkdir -p "$work/float_clean"
cat >"$work/float_clean/model.py" <<'PY'
from decimal import Decimal
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

balance: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)

# The word float appearing in prose must not trip the guard.
def to_float_is_forbidden() -> None:
    """Never convert money to float."""
PY
expect 0 "passes on Numeric(19, 2)" "$here/check_no_float.sh" "$work/float_clean"

expect 2 "errors on a missing directory" "$here/check_no_float.sh" "$work/nope"

# ── check_no_public_api_url ───────────────────────────────────────────────────
echo "check_no_public_api_url.sh"

mkdir -p "$work/url_dirty/src"
cat >"$work/url_dirty/src/config.ts" <<'TS'
export const base = process.env.NEXT_PUBLIC_API_URL;
TS
expect 1 "fails on NEXT_PUBLIC_API_URL" "$here/check_no_public_api_url.sh" "$work/url_dirty"

mkdir -p "$work/url_dirty2/src"
cat >"$work/url_dirty2/src/client.ts" <<'TS'
export const ready = () => fetch("http://api:8000/ready");
TS
expect 1 "fails on a hardcoded API origin" "$here/check_no_public_api_url.sh" "$work/url_dirty2"

mkdir -p "$work/url_dirty3/src"
cat >"$work/url_dirty3/src/.env.local" <<'ENV'
NEXT_PUBLIC_API_URL=http://api:8000
ENV
expect 1 "fails on the var assigned in an env file" \
  "$here/check_no_public_api_url.sh" "$work/url_dirty3"

mkdir -p "$work/url_clean/src"
cat >"$work/url_clean/src/client.ts" <<'TS'
// There is deliberately no NEXT_PUBLIC_API_URL here — naming it in a comment that
// explains the rule must not trip the guard, or the guard gets silenced.
export const ready = () => fetch("/api/ready");
TS
cat >"$work/url_clean/src/client.test.ts" <<'TS'
// A test asserting rejection legitimately contains an absolute URL.
it("rejects", () => expect(() => apiPath("http://api:8000/ready")).toThrow());
TS
expect 0 "passes on relative paths, ignoring test files" \
  "$here/check_no_public_api_url.sh" "$work/url_clean"

expect 2 "errors on a missing directory" "$here/check_no_public_api_url.sh" "$work/nope"

# ── result ────────────────────────────────────────────────────────────────────
echo ""
echo "guards: $passed passed, $failed failed"
[[ $failed -eq 0 ]]
