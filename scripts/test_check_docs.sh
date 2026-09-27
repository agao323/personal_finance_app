#!/usr/bin/env bash
#
# Tests for scripts/check_docs.py — the same pattern as test_guards.sh.
#
# A check that never fires is indistinguishable from a broken one. So: build a small
# repository that passes every doc check, prove it passes, then break it one way at a time
# and prove the matching check fails.
#
# Fixture text writes @D@ for the docs directory and @A@ for ARCHITECTURE. check_docs.py
# scans this file too, as code that cites docs paths; spelled out, the deliberately broken
# paths below would fail the real check.

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

# expect_fail <name> <pattern> <cmd...>: exit 1, and the output names *this* problem —
# so a variant cannot pass because something else in it happened to be broken.
expect_fail() {
  local name="$1" pattern="$2"
  shift 2
  local out
  out=$("$@" 2>&1)
  local got=$?
  if [[ $got -eq 1 ]] && grep -qE -- "$pattern" <<<"$out"; then
    echo "  ok    $name"
    passed=$((passed + 1))
  else
    echo "  FAIL  $name (expected exit 1 naming /$pattern/, got $got)"
    echo "$out" | sed 's/^/          /'
    failed=$((failed + 1))
  fi
}

check_docs() {
  uv run --project "$here/../api" --quiet python "$here/check_docs.py" "$@"
}

# put <file>: write stdin to <file>, expanding the placeholders.
put() {
  mkdir -p "$(dirname "$1")"
  sed -e 's/@D@/docs/g' -e 's/@A@/ARCHITECTURE/g' >"$1"
}

# append <file>: append stdin to <file>, expanding the placeholders.
append() {
  sed -e 's/@D@/docs/g' -e 's/@A@/ARCHITECTURE/g' >>"$1"
}

# edit <file> <sed expression>: portable in-place edit (BSD and GNU sed differ on -i).
edit() {
  sed -e 's/@D@/docs/g' -e "$2" "$1" >"$1.tmp" && mv "$1.tmp" "$1"
}

# variant <name>: a fresh copy of the clean fixture.
variant() {
  cp -R "$clean" "$work/$1"
  echo "$work/$1"
}

# ── the clean fixture ─────────────────────────────────────────────────────────

clean="$work/clean"

put "$clean/AGENTS.md" <<'MD'
# AGENTS
[plans](@D@/PLANS.md) · [design](@D@/design-docs/index.md) · [specs](@D@/product-specs/index.md)
· [refs](@D@/references/index.md) · [adrs](@D@/adr/README.md) · [plans index](@D@/generated/exec-plans.md)
· [architecture](@D@/@A@.md)
MD
printf '@AGENTS.md\n' >"$clean/CLAUDE.md"

put "$clean/docs/PLANS.md" <<'MD'
# Plans

## Tests

Every plan ships tests.
MD
put "$clean/docs/ARCHITECTURE.md" <<'MD'
# Architecture

## Layers

| Invariant |
|---|
| <a id="money"></a>Money is cents |
MD
put "$clean/docs/DECISIONS.md" <<'MD'
# Decisions
MD
put "$clean/docs/design-docs/index.md" <<'MD'
# Design docs

Also see [the decisions](../DECISIONS.md), described below.

| Doc | Status | Last verified |
|---|---|---|
| [a](a.md) | current | 2026-09-27 |
| [0001](../adr/0001-x.md) | superseded by nothing yet | 2026-09-27 |
| [decisions](../DECISIONS.md) | current | 2026-09-27 |
MD
put "$clean/docs/design-docs/a.md" <<'MD'
# A

See [tests](../PLANS.md#tests) and [money](../@A@.md#money).

```
[not a link, it is in a fence](nowhere.md)
```
MD
put "$clean/docs/adr/README.md" <<'MD'
# ADRs

| `0001-x.md` | written |
MD
put "$clean/docs/adr/0001-x.md" <<'MD'
# 0001 — X
MD
put "$clean/docs/product-specs/index.md" <<'MD'
# Specs

[s](s.md)
MD
put "$clean/docs/product-specs/s.md" <<'MD'
# S
MD
put "$clean/docs/references/index.md" <<'MD'
# References

[r](r-llms.txt)
MD
printf 'notes\n' >"$clean/docs/references/r-llms.txt"
put "$clean/docs/exec-plans/tech-debt-tracker.md" <<'MD'
# Tech-debt tracker
MD
put "$clean/docs/exec-plans/completed/001-first.md" <<'MD'
# 001 — First
Status: done
Wave: 0   Lane: —
Blocked by: none
Read first: @D@/PLANS.md#tests

## Goal
Done.
MD
put "$clean/docs/exec-plans/active/002-second.md" <<'MD'
# 002 — Second
Status: todo — needs a decision
Wave: 1   Lane: A
Blocked by: 001
Read first: @D@/PLANS.md, @D@/@A@.md#money

## Goal
Not yet.
MD
put "$clean/api/app/x.py" <<'PY'
"""See @D@/PLANS.md#tests and @A@#money, and ../../@D@/design-docs/a.md."""
PY
# data/ must never be opened: a broken link in it has to go unnoticed.
put "$clean/data/README.md" <<'MD'
[broken on purpose](nowhere.md)
MD
check_docs --root "$clean" --write-plan-index >/dev/null

echo "check_docs.py"
expect 0 "passes on a clean repository (and never reads data/)" check_docs --root "$clean"

# ── 1. map ────────────────────────────────────────────────────────────────────
r=$(variant long_agents)
for _ in $(seq 1 101); do echo "line" >>"$r/AGENTS.md"; done
expect_fail "map: fails when AGENTS.md is over 100 lines" 'lines, over the limit' check_docs --root "$r" map

r=$(variant fat_claude)
echo "More instructions" >>"$r/CLAUDE.md"
expect_fail "map: fails when CLAUDE.md is more than the import" 'contains more than' check_docs --root "$r" map

# ── 2. links ──────────────────────────────────────────────────────────────────
r=$(variant broken_link)
echo "[gone](missing.md)" >>"$r/docs/design-docs/a.md"
expect_fail "links: fails on a link to a missing file" 'link to missing missing\.md' check_docs --root "$r" links

r=$(variant broken_anchor)
echo "[gone](../PLANS.md#nope)" >>"$r/docs/design-docs/a.md"
expect_fail "links: fails on a link to a missing anchor" 'link to missing anchor \.\./PLANS\.md#nope' check_docs --root "$r" links

r=$(variant broken_self_anchor)
echo "[gone](#nope)" >>"$r/docs/design-docs/a.md"
expect_fail "links: fails on a missing anchor in the same file" 'link to missing anchor #nope' check_docs --root "$r" links

r=$(variant code_missing_doc)
printf '# See @D@/gone.md\n' | put "$r/api/app/y.py"
expect_fail "links: fails when code cites a missing doc" 'cites missing .*gone\.md' check_docs --root "$r" links

r=$(variant code_missing_anchor)
printf '# See @D@/PLANS.md#nope\n' | put "$r/api/app/y.py"
expect_fail "links: fails when code cites a missing anchor" 'cites missing anchor .*PLANS\.md#nope' check_docs --root "$r" links

r=$(variant code_shorthand)
printf '# See @A@#nope\n' | put "$r/web/src/y.ts"
expect_fail "links: fails on a missing anchor in the ARCHITECTURE-hash shorthand" 'cites missing anchor .*ARCHITECTURE\.md#nope' check_docs --root "$r" links

# ── 3. reachable ──────────────────────────────────────────────────────────────
r=$(variant orphan)
printf '# Orphan\n' | put "$r/docs/design-docs/orphan.md"
expect_fail "reachable: fails on a doc nothing links to" 'orphan\.md: not linked' check_docs --root "$r" reachable

r=$(variant too_deep)
printf '# Deep\n' | put "$r/docs/design-docs/deep.md"
echo "[deep](deep.md)" >>"$r/docs/design-docs/a.md"
expect_fail "reachable: fails on a doc three links from AGENTS.md" 'deep\.md: 3 links from AGENTS\.md' check_docs --root "$r" reachable

r=$(variant image_orphan)
printf 'png' >"$r/docs/diagram.png"
expect_fail "reachable: covers every file under docs/, not only markdown" 'diagram\.png: not linked' check_docs --root "$r" reachable

# ── 4. indexes ────────────────────────────────────────────────────────────────
r=$(variant unindexed_design_doc)
printf '# B\n' | put "$r/docs/design-docs/b.md"
echo "[b](@D@/design-docs/b.md)" | append "$r/AGENTS.md"
expect_fail "indexes: fails when a design doc is missing from its index" 'does not list .*b\.md' check_docs --root "$r" indexes

r=$(variant no_status)
edit "$r/docs/design-docs/index.md" 's/| \[a\](a.md) | current |/| [a](a.md) | |/'
expect_fail "indexes: fails when a design-doc row has no status" 'has no status' check_docs --root "$r" indexes

r=$(variant no_date)
edit "$r/docs/design-docs/index.md" 's/| \[a\](a.md) | current | 2026-09-27 |/| [a](a.md) | current | never |/'
expect_fail "indexes: fails when a design-doc row has no date" 'has no last-verified date' check_docs --root "$r" indexes

r=$(variant unindexed_adr)
printf '# 0002 — Y\n' | put "$r/docs/adr/0002-y.md"
echo "| [0002](../adr/0002-y.md) | current | 2026-09-27 |" >>"$r/docs/design-docs/index.md"
expect_fail "indexes: fails when an ADR is missing from adr/README.md" 'does not list 0002-y\.md' check_docs --root "$r" indexes

r=$(variant unindexed_spec)
printf '# S2\n' | put "$r/docs/product-specs/s2.md"
expect_fail "indexes: fails when a spec is missing from its index" 'does not link s2\.md' check_docs --root "$r" indexes

r=$(variant unindexed_reference)
printf 'more notes\n' >"$r/docs/references/r2-llms.txt"
expect_fail "indexes: fails when a reference is missing from its index" 'does not link r2-llms\.txt' check_docs --root "$r" indexes

# ── 5. plans ──────────────────────────────────────────────────────────────────
r=$(variant bad_status)
edit "$r/docs/exec-plans/completed/001-first.md" 's/^Status: done$/Status: finished/'
expect_fail "plans: fails on an unknown status" 'unknown status .finished.' check_docs --root "$r" plans

r=$(variant wrong_folder)
mv "$r/docs/exec-plans/completed/001-first.md" "$r/docs/exec-plans/active/001-first.md"
expect_fail "plans: fails when the folder does not match the status" 'belongs in exec-plans/completed/' check_docs --root "$r" plans

r=$(variant duplicate_id)
cp "$r/docs/exec-plans/active/002-second.md" "$r/docs/exec-plans/active/002-again.md"
expect_fail "plans: fails on a duplicate ID" 'duplicate ID 002' check_docs --root "$r" plans

r=$(variant unknown_blocker)
edit "$r/docs/exec-plans/active/002-second.md" 's/^Blocked by: 001$/Blocked by: 999/'
expect_fail "plans: fails when Blocked by names a plan that does not exist" 'names 999, which has no plan' check_docs --root "$r" plans

r=$(variant no_blocked_by)
edit "$r/docs/exec-plans/active/002-second.md" '/^Blocked by:/d'
expect_fail "plans: fails when a required field is missing" 'missing .Blocked by:.' check_docs --root "$r" plans

r=$(variant no_read_first)
edit "$r/docs/exec-plans/active/002-second.md" '/^Read first:/d'
expect_fail "plans: fails when an active plan has no Read first" 'active plan has no .Read first:.' check_docs --root "$r" plans

r=$(variant missing_read_first)
edit "$r/docs/exec-plans/active/002-second.md" 's/^Read first: .*/Read first: @D@\/gone.md/'
expect_fail "plans: fails when Read first names a missing doc" 'Read first names missing .*gone\.md' check_docs --root "$r" plans

r=$(variant title_mismatch)
edit "$r/docs/exec-plans/active/002-second.md" 's/^# 002 — Second$/# 003 — Second/'
expect_fail "plans: fails when the title ID and filename disagree" 'first line is not' check_docs --root "$r" plans

r=$(variant stray_ticket)
mkdir -p "$r/tickets"
cp "$r/docs/exec-plans/active/002-second.md" "$r/tickets/003-stray.md"
expect_fail "plans: fails on a plan left outside docs/exec-plans/" 'a plan outside' check_docs --root "$r" plans

# ── 6. the generated plan index ───────────────────────────────────────────────
r=$(variant stale_index)
edit "$r/docs/exec-plans/active/002-second.md" 's/^Status: todo — needs a decision$/Status: in-progress/'
expect_fail "plan-index: fails when a header changed without make docs" 'out of date with the plan headers' check_docs --root "$r" plan-index

r=$(variant missing_index)
rm "$r/docs/generated/exec-plans.md"
expect_fail "plan-index: fails when the index is missing" 'exec-plans\.md: missing' check_docs --root "$r" plan-index

# ── usage ─────────────────────────────────────────────────────────────────────
expect 2 "errors on a missing root" check_docs --root "$work/nope"
expect 2 "errors on an unknown check" check_docs --root "$clean" nonsense

r=$(variant fix_message)
echo "[gone](missing.md)" >>"$r/docs/design-docs/a.md"
expect_fail "a failure states the rule" '^  Rule: ' check_docs --root "$r" links
expect_fail "a failure names the doc" '^  Doc:  ' check_docs --root "$r" links
expect_fail "a failure says how to fix it" '^  Fix:  ' check_docs --root "$r" links

# ── result ────────────────────────────────────────────────────────────────────
echo ""
echo "check_docs: $passed passed, $failed failed"
[[ $failed -eq 0 ]]
