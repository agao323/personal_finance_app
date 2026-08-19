#!/usr/bin/env bash
# The demo's database must be a different Neon PROJECT, not a branch and not the same
# database with a different name.
#
# Neon encodes the project in the host: ep-<endpoint>.<region>.aws.neon.tech, where
# the endpoint id belongs to exactly one project. Two URLs sharing an endpoint id are
# the same project — which is the failure this exists to catch, because a branch of
# the real project shares credentials and an account with it.
#
# Reads two environment variables and never prints either. A guard that echoes a
# connection string into a build log has created the disclosure it was meant to
# prevent.
set -euo pipefail

fail() { echo "  FAIL: $1" >&2; exit 1; }

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${DEMO_DATABASE_URL:?DEMO_DATABASE_URL is required}"

[ "$DATABASE_URL" != "$DEMO_DATABASE_URL" ] || fail "the demo and real database URLs are identical"

host_of() {
  # scheme://user:pass@HOST:port/db?params  → HOST
  printf '%s' "$1" | sed -E 's|^[^/]*//||; s|^[^@]*@||; s|[:/?].*$||'
}

endpoint_of() {
  # ep-nameless-sun-aye4116n.c-5.us-east-2.aws.neon.tech → ep-nameless-sun-aye4116n
  # The pooled host appends "-pooler" to the endpoint id; strip it so a pooled and an
  # unpooled URL for the same project still compare equal.
  printf '%s' "$1" | sed -E 's|\..*$||; s|-pooler$||'
}

real_host="$(host_of "$DATABASE_URL")"
demo_host="$(host_of "$DEMO_DATABASE_URL")"
real_endpoint="$(endpoint_of "$real_host")"
demo_endpoint="$(endpoint_of "$demo_host")"

[ -n "$real_endpoint" ] || fail "could not read an endpoint from DATABASE_URL"
[ -n "$demo_endpoint" ] || fail "could not read an endpoint from DEMO_DATABASE_URL"

if [ "$real_endpoint" = "$demo_endpoint" ]; then
  fail "the demo shares a Neon endpoint with the real database — that is a branch, not a separate project"
fi

echo "  ok: the demo uses a different Neon endpoint from the real database"
